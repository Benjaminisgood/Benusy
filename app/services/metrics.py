import random


async def fetch_metrics(post_url: str) -> dict[str, int]:
    if not post_url.startswith("http"):
        raise ValueError("Invalid post URL")

    # Simulate integration instability: some links require manual fallback.
    if random.random() < 0.2:
        raise RuntimeError("Auto metrics fetch failed")

    return {
        "likes": random.randint(50, 1500),
        "comments": random.randint(10, 700),
        "shares": random.randint(5, 300),
        "views": random.randint(500, 50000),
    }
