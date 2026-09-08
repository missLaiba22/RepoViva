from fastapi import APIRouter, Depends

from core_api.auth.dependencies import get_current_user
from core_api.users.models import User
from core_api.users.schemas import UserRead

router = APIRouter(prefix="/v1", tags=["users"])


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user