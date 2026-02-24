from sqlmodel import SQLModel


class HomepageConfigRead(SQLModel):
    site_name: str
    nav_brand: str
    hero_title: str
    hero_subtitle: str
    hero_image_url: str


class OSSPublicConfigRead(SQLModel):
    enabled: bool
    endpoint: str
    bucket: str
    prefix: str


class PublicConfigRead(SQLModel):
    homepage: HomepageConfigRead
    oss: OSSPublicConfigRead
