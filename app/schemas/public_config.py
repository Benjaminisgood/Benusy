from sqlmodel import SQLModel


class HomepageConfigRead(SQLModel):
    site_name: str
    nav_brand: str
    hero_title: str
    hero_subtitle: str
    hero_image_url: str
    hero_primary_button_text: str
    hero_primary_button_href: str
    hero_secondary_button_text: str
    hero_secondary_button_href: str
    merchant_notice_title: str
    merchant_notice_text: str
    merchant_service_publish_text: str
    merchant_service_account_text: str
    merchant_service_no_register_text: str
    merchant_contact_phone: str
    merchant_contact_wechat: str
    merchant_contact_email: str
    contact_section_title: str
    contact_section_subtitle: str
    contact_address: str
    contact_phone: str
    contact_email: str


class OSSPublicConfigRead(SQLModel):
    enabled: bool
    endpoint: str
    bucket: str
    prefix: str


class PublicConfigRead(SQLModel):
    homepage: HomepageConfigRead
    oss: OSSPublicConfigRead
