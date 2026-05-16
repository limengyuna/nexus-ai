"""
认证 API 单测

验证：
1. 注册 → 201 + 返回用户信息
2. 登录 → 返回 access_token
3. 错误密码 → 401
"""


class TestAuth:
    def test_register_then_login(self, client):
        """注册成功后，可用同样凭证登录拿到 token"""
        # 注册
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "test_register_user", "password": "pwd12345"},
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["data"]["username"] == "test_register_user"
        # 密码不应回显
        assert "password" not in data["data"]
        assert "hashed_password" not in data["data"]

        # 登录
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "test_register_user", "password": "pwd12345"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        token = resp.json()["data"]["access_token"]
        assert isinstance(token, str) and len(token) > 20

    def test_login_with_wrong_password_returns_401(self, client):
        """错误密码不能登录"""
        # 先注册
        client.post(
            "/api/v1/auth/register",
            json={"username": "wrong_pwd_user", "password": "correct_pwd"},
        )
        # 错误密码
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "wrong_pwd_user", "password": "wrong_pwd"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 401

    def test_get_me_requires_auth(self, client):
        """/auth/me 未带 token 应 401"""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401
