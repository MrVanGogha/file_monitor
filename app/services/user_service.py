from typing import Optional
import json

from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import User
from app.repositories.user_repository import UserRepository

try:
    import redis.asyncio as redis
except Exception:  # pragma: no cover - allow runtime without redis installed
    redis = None  # type: ignore


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, session: AsyncSession, redis_client: Optional["redis.Redis"] = None):
        self.repo = UserRepository(session)
        self.session = session
        self.redis = redis_client

    def _hash_password(self, plain_password: str) -> str:
        return pwd_context.hash(plain_password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def _cache_key(self, user_id: int) -> str:
        return f"user:{user_id}"

    async def _cache_get(self, user_id: int) -> Optional[User]:
        if not self.redis:
            return None
        data = await self.redis.get(self._cache_key(user_id))
        if not data:
            return None
        obj = json.loads(data)
        # Map cached dict back to ORM-like object (minimal fields)
        user = User(
            id=obj["id"],
            username=obj["username"],
            email=obj["email"],
            hashed_password=obj.get("hashed_password", ""),
            is_active=obj.get("is_active", True),
        )
        return user

    async def _cache_set(self, user: User) -> None:
        if not self.redis:
            return
        obj = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            # Don't expose hashed_password in cache unless needed; included here for symmetry but can be omitted
            # "hashed_password": user.hashed_password,
        }
        await self.redis.set(self._cache_key(user.id), json.dumps(obj), ex=300)

    async def _cache_delete(self, user_id: int) -> None:
        if not self.redis:
            return
        await self.redis.delete(self._cache_key(user_id))

    async def create_user(self, username: str, email: str, password: str) -> User:
        existing = await self.repo.get_by_username(username)
        if existing:
            raise ValueError("Username already exists")
        user = User(
            username=username,
            email=email,
            hashed_password=self._hash_password(password),
        )
        user = await self.repo.create(user)
        await self.session.commit()
        await self.session.refresh(user)
        await self._cache_set(user)
        return user

    async def get_user(self, user_id: int) -> Optional[User]:
        cached = await self._cache_get(user_id)
        if cached:
            return cached
        user = await self.repo.get_by_id(user_id)
        if user:
            await self._cache_set(user)
        return user

    async def list_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        return await self.repo.list(limit=limit, offset=offset)

    async def delete_user(self, user_id: int) -> None:
        user = await self.repo.get_by_id(user_id)
        if not user:
            return
        await self.repo.delete(user)
        await self.session.commit()
        await self._cache_delete(user_id)