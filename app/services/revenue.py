from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from app.models import Metric, PlatformMetricConfig


@dataclass(frozen=True)
class RevenueConfig:
    platform_coef: float = 1.0
    like_weight: float = 1.0
    favorite_weight: float = 2.0
    share_weight: float = 3.0
    view_weight: float = 0.01


def get_revenue_config(session: Session, platform: str) -> RevenueConfig:
    platform_config = session.exec(
        select(PlatformMetricConfig).where(PlatformMetricConfig.platform == platform)
    ).first()
    if platform_config:
        return RevenueConfig(
            platform_coef=platform_config.platform_coef,
            like_weight=platform_config.like_weight,
            favorite_weight=platform_config.favorite_weight,
            share_weight=platform_config.share_weight,
            view_weight=platform_config.view_weight,
        )

    default_config = session.exec(
        select(PlatformMetricConfig).where(PlatformMetricConfig.platform == "default")
    ).first()
    if default_config:
        return RevenueConfig(
            platform_coef=default_config.platform_coef,
            like_weight=default_config.like_weight,
            favorite_weight=default_config.favorite_weight,
            share_weight=default_config.share_weight,
            view_weight=default_config.view_weight,
        )

    return RevenueConfig()


def calculate_engagement_score(metric: Metric, config: RevenueConfig) -> float:
    return (
        metric.likes * config.like_weight
        + metric.favorites * config.favorite_weight
        + metric.shares * config.share_weight
        + metric.views * config.view_weight
    )


def calculate_revenue(
    *,
    base_reward: float,
    user_weight: float,
    engagement_score: float,
    platform_coef: float,
) -> float:
    return round(base_reward + engagement_score * platform_coef * user_weight, 2)
