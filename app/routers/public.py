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
            hero_primary_button_text=settings.homepage_hero_primary_button_text,
            hero_primary_button_href=settings.homepage_hero_primary_button_href,
            hero_secondary_button_text=settings.homepage_hero_secondary_button_text,
            hero_secondary_button_href=settings.homepage_hero_secondary_button_href,
            merchant_notice_title=settings.homepage_merchant_notice_title,
            merchant_notice_text=settings.homepage_merchant_notice_text,
            merchant_service_publish_text=settings.homepage_merchant_service_publish_text,
            merchant_service_account_text=settings.homepage_merchant_service_account_text,
            merchant_service_no_register_text=settings.homepage_merchant_service_no_register_text,
            merchant_contact_phone=settings.homepage_merchant_contact_phone,
            merchant_contact_wechat=settings.homepage_merchant_contact_wechat,
            merchant_contact_email=settings.homepage_merchant_contact_email,
            contact_section_title=settings.homepage_contact_section_title,
            contact_section_subtitle=settings.homepage_contact_section_subtitle,
            contact_address=settings.homepage_contact_address,
            contact_phone=settings.homepage_contact_phone,
            contact_email=settings.homepage_contact_email,
        ),
        oss=OSSPublicConfigRead(
            enabled=settings.oss_enabled(),
            endpoint=settings.aliyun_oss_endpoint,
            bucket=settings.aliyun_oss_bucket,
            prefix=settings.aliyun_oss_prefix,
        ),
    )
