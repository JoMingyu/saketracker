import asyncio
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import md5
from typing import Set

import arrow
import discord
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests import get


@dataclass
class Sake:
    provider: str
    name: str
    price_yen: str
    # url: str

    def __hash__(self):
        return int(md5(self.name.encode()).hexdigest(), 16)


class Source(ABC):
    def __init__(self, provider_name: str):
        self.count = 0
        self.provider_name = provider_name
        self.previous_result = self.get_sakes()

    @abstractmethod
    def get_sakes(self) -> Set[Sake]:
        pass

    def run(self) -> Set[Sake]:
        new_result = self.get_sakes()

        if diffs := (new_result - self.previous_result):
            self.previous_result = new_result

            return diffs
        else:
            return set()


class Sake09(Source):
    def __init__(self):
        super().__init__("sake09")

    def get_sakes(self) -> Set[Sake]:
        result = set()

        resp = get(
            "https://sake09.com/shop/products/list.php?category_id=64&disp_number=300",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"
            },
        )

        if resp.status_code != 200:
            raise Exception(f"{resp.status_code} occurred.")

        bs = BeautifulSoup(resp.text, "html.parser")

        divs = bs.select("div.list_area.clearfix")

        for div in divs:
            *others, div_name, div_price = div.select("div")

            # product_id = int(div_name.select_one("h3 > a").get("href").split("=")[-1])

            result.add(
                Sake(
                    provider=self.provider_name,
                    name=div_name.select_one("h3 > a").text,
                    price_yen="¥" + div_price.select_one("span > span > b").text,
                    # url=f"https://sake09.com/shop/products/detail.php?product_id={product_id}",
                )
            )

        return result


class Sakedoo(Source):
    def __init__(self):
        super().__init__("sakedoo")

    def get_sakes(self) -> Set[Sake]:
        result = set()

        resp = get(
            "https://sakedoo.com/collections/%ED%95%9C%EC%A0%95%ED%8C%90%EB%A7%A4-%EC%84%B8%EC%9D%BC?sort_by=manual",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"
            },
        )

        if resp.status_code != 200:
            raise Exception(f"{resp.status_code} occurred.")

        products = json.loads(re.findall(r"var meta = (.+);", resp.text)[0])["products"]

        for product in products:
            for variant in product["variants"]:
                if variant["public_title"] == "none":
                    result.add(
                        Sake(
                            provider=self.provider_name,
                            name=variant["name"].rstrip(" - none"),
                            price_yen=f"¥{variant['price'] // 100}",
                            # url=f"https://sakedoo.com/products/{product['handle']}",
                        )
                    )

        return result


client = discord.Client()


async def my_background_task():
    await client.wait_until_ready()

    channel = client.get_channel(id=882654869809418271)
    debug_channel = client.get_channel(id=984273411176009779)

    try:
        providers = [Sake09(), Sakedoo()]

        await debug_channel.send(f"{datetime.now(timezone.utc)}: Start.")
    except Exception as e:
        await debug_channel.send(f"{e}")
        return

    provider_to_sleep_seconds = {
        "sake09": [5, 300],
        "sakedoo": [5, 300],
    }

    while not client.is_closed():
        for provider in providers:
            try:
                diffs = provider.run()

                if diffs:
                    for sake in diffs:
                        await channel.send(
                            f"""상품 발견! ({arrow.now('Asia/Seoul').format('YYYY-MM-DD HH:mm:ss')})
    [{provider.provider_name}] {sake.name} ({sake.price_yen}円)"""
                        )

                provider_to_sleep_seconds[provider.provider_name] = [5, 300]
            except Exception as e:
                await debug_channel.send(
                    f"""에러 발생! ({arrow.now('Asia/Seoul').format('YYYY-MM-DD HH:mm:ss')})
    [{provider.provider_name}] {e}"""
                )

                provider_to_sleep_seconds[provider.provider_name] = [300, 3600]

            now = datetime.now(tz=timezone(timedelta(hours=9)))

            if now.hour < 8 or now.hour > 18:
                await asyncio.sleep(
                    provider_to_sleep_seconds[provider.provider_name][1]
                )
            else:
                await asyncio.sleep(
                    provider_to_sleep_seconds[provider.provider_name][0]
                )


@client.event
async def on_ready():
    print("Logged in as")
    print(client.user.name)
    print(client.user.id)
    print("------")


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

client.loop.create_task(my_background_task())
client.run(TOKEN)
