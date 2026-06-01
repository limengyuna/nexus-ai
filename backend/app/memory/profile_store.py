from typing import Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, delete

from app.models.memory_profile import MemorySlot, UserMemorySlotValue, MemoryCandidate
from app.memory.profile_slots import DEFAULT_MEMORY_SLOTS, DEPRECATED_MEMORY_SLOT_KEYS


class MemoryProfileStore:
    @staticmethod
    def init_default_slots(db: Session) -> None:
        """
        初始化系统预设的 profile slots。
        使用 upsert 逻辑。
        """
        for slot_data in DEFAULT_MEMORY_SLOTS:
            slot_key = slot_data["slot_key"]
            existing = db.execute(select(MemorySlot).where(MemorySlot.slot_key == slot_key)).scalar_one_or_none()
            if existing:
                existing.slot_type = slot_data["slot_type"]
                existing.value_type = slot_data.get("value_type", "string")
                existing.description = slot_data.get("description")
                existing.allowed_values = slot_data.get("allowed_values")
                existing.is_active = True
            else:
                new_slot = MemorySlot(**slot_data)
                db.add(new_slot)
        if DEPRECATED_MEMORY_SLOT_KEYS:
            deprecated_slots = db.execute(
                select(MemorySlot).where(MemorySlot.slot_key.in_(DEPRECATED_MEMORY_SLOT_KEYS))
            ).scalars().all()
            for slot in deprecated_slots:
                slot.is_active = False
        db.commit()

    @staticmethod
    def list_active_slots(db: Session) -> List[MemorySlot]:
        """列出系统所有可用的槽位"""
        stmt = select(MemorySlot).where(MemorySlot.is_active == True)
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def get_user_profile(
        db: Session,
        user_id: int,
        slot_types: Optional[List[str]] = None,
    ) -> List[UserMemorySlotValue]:
        """获取特定用户的结构化档案"""
        stmt = (
            select(UserMemorySlotValue)
            .join(MemorySlot, UserMemorySlotValue.slot_id == MemorySlot.id)
            .where(UserMemorySlotValue.user_id == user_id, UserMemorySlotValue.is_active == True)
        )
        if slot_types:
            stmt = stmt.where(MemorySlot.slot_type.in_(slot_types))
            
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def upsert_slot_value(
        db: Session,
        *,
        user_id: int,
        slot_key: str,
        slot_value: Any,
        confidence: float,
        source: str,
        source_session_id: Optional[int] = None,
        source_message_id: Optional[int] = None,
        updated_by: str = "assistant",
    ) -> Optional[UserMemorySlotValue]:
        """
        写入/更新用户的某个槽位值。
        如果槽位不存在或未启用，则转为 candidate。
        带乐观并发控制（依据 source_message_id）。
        """
        slot = db.execute(select(MemorySlot).where(MemorySlot.slot_key == slot_key)).scalar_one_or_none()
        if not slot or not slot.is_active:
            # 找不到该槽位，写入 candidate
            MemoryProfileStore.create_candidate(
                db,
                user_id=user_id,
                candidate_text=f"提取的值为: {slot_value}",
                suggested_slot_key=slot_key,
                suggested_value=slot_value,
                reason="对应槽位不存在或未激活",
                confidence=confidence,
                source_session_id=source_session_id,
                source_message_id=source_message_id,
            )
            return None

        # 检查是否已存在
        existing = db.execute(
            select(UserMemorySlotValue)
            .where(UserMemorySlotValue.user_id == user_id, UserMemorySlotValue.slot_id == slot.id)
        ).scalar_one_or_none()

        if existing:
            # 竞态/乱序保护
            if existing.source == "manual" and source == "inferred":
                return existing  # 手动覆盖高于 inferred
                
            if existing.source_message_id and source_message_id:
                if source_message_id < existing.source_message_id:
                    return existing  # 忽略旧消息提取的数据

            # 如果新值一模一样，直接返回不触发 update
            if existing.slot_value == slot_value:
                return existing

            existing.slot_value = slot_value
            existing.confidence = confidence
            existing.source = source
            existing.source_session_id = source_session_id
            existing.source_message_id = source_message_id
            existing.updated_by = updated_by
            existing.is_active = True
        else:
            new_val = UserMemorySlotValue(
                user_id=user_id,
                slot_id=slot.id,
                slot_value=slot_value,
                confidence=confidence,
                source=source,
                source_session_id=source_session_id,
                source_message_id=source_message_id,
                updated_by=updated_by,
            )
            db.add(new_val)
            existing = new_val

        db.commit()
        db.refresh(existing)
        return existing

    @staticmethod
    def delete_slot_value(
        db: Session,
        user_id: int,
        slot_key: str,
    ) -> bool:
        """手动删除某个槽位值"""
        slot = db.execute(select(MemorySlot).where(MemorySlot.slot_key == slot_key)).scalar_one_or_none()
        if not slot:
            return False
            
        stmt = delete(UserMemorySlotValue).where(
            and_(UserMemorySlotValue.user_id == user_id, UserMemorySlotValue.slot_id == slot.id)
        )
        res = db.execute(stmt)
        db.commit()
        return res.rowcount > 0

    @staticmethod
    def create_candidate(
        db: Session,
        *,
        user_id: int,
        candidate_text: str,
        suggested_slot_key: Optional[str] = None,
        suggested_value: Optional[Any] = None,
        reason: str,
        confidence: float,
        source_session_id: Optional[int] = None,
        source_message_id: Optional[int] = None,
    ) -> MemoryCandidate:
        """创建候选记忆（自带防洪水去重逻辑）"""
        import hashlib
        
        # 计算去重哈希
        raw_str = f"{user_id}:{suggested_slot_key}:{candidate_text.strip().lower()}"
        dedupe_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

        existing = db.execute(
            select(MemoryCandidate).where(
                MemoryCandidate.user_id == user_id, MemoryCandidate.dedupe_hash == dedupe_hash
            )
        ).scalar_one_or_none()

        if existing:
            existing.seen_count += 1
            existing.confidence = max(existing.confidence, confidence)
            existing.reason = reason
            existing.source_session_id = source_session_id
            existing.source_message_id = source_message_id
            db.commit()
            db.refresh(existing)
            return existing
        else:
            new_cand = MemoryCandidate(
                user_id=user_id,
                candidate_text=candidate_text,
                suggested_slot_key=suggested_slot_key,
                suggested_value=suggested_value,
                reason=reason,
                confidence=confidence,
                dedupe_hash=dedupe_hash,
                status="pending",
                source_session_id=source_session_id,
                source_message_id=source_message_id,
            )
            db.add(new_cand)
            db.commit()
            db.refresh(new_cand)
            return new_cand
