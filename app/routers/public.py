from fastapi import APIRouter

from app.core.config import settings
from app.schemas.public_config import HomepageConfigRead, OSSPublicConfigRead, PublicConfigRead

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/config", response_model=PublicConfigRead)
def get_public_config() -> PublicConfigRead:
    return PublicConfigRead(
        homepage=HomepageConfigRead(
            site_name=settings.app_name,
            nav_brand=settings.homepage_nav_brand,
            hero_title=settings.homepage_hero_title,
            hero_subtitle=settings.homepage_hero_subtitle,
            hero_image_url=settings.homepage_hero_image_url,
        ),
        oss=OSSPublicConfigRead(
            enabled=settings.oss_enabled(),
            endpoint=settings.aliyun_oss_endpoint,
            bucket=settings.aliyun_oss_bucket,
            prefix=settings.aliyun_oss_prefix,
        ),
    )
