import json
import os
import time
import requests

from notion_tools.defaults import NotionToolsDefaults as NTD


class NotionTools:
    NOTION_API_VERSION = "2022-06-28"

    def __init__(self, token):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": self.NOTION_API_VERSION,
        }

    @staticmethod
    def from_file(token_file=None):
        if token_file is None:
            token_file = NTD.NOTION_TOKEN_FILE
        with open(os.path.expanduser(token_file), "r") as f:
            secrets = json.load(f)
        return NotionTools(secrets["auth"])

    def _create_bulleted_list(self, data, level=0):
        if not isinstance(data, list):
            raise ValueError("Input data must be a list.")
        notion_blocks = []
        for item in data:
            if isinstance(item, list):
                nested_blocks = self._create_bulleted_list(item, level + 1)
                if notion_blocks:
                    notion_blocks[-1]["bulleted_list_item"]["children"] = nested_blocks
                else:
                    raise ValueError("Nested list structure is invalid.")
            else:
                block = {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": str(item)}}]
                    },
                }
                notion_blocks.append(block)
        return notion_blocks

    def append_blocks(self, page_id, text):
        ps = [p for p in text.split("\n") if p.strip()]
        data = {
            "children": self._create_bulleted_list(
                [ps[0], ps[1:]] if len(ps) > 1 else [ps[0]]
            )
        }
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        response = requests.patch(url, json=data, headers=self.headers)
        if response.status_code != 200:
            raise Exception(f"Error appending blocks: {response.status_code}, {response.text}")

    def get_page_blocks(self, page_id):
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        has_more = True
        next_cursor = None
        all_blocks = []

        while has_more:
            params = {}
            if next_cursor:
                time.sleep(0.3)
                params["start_cursor"] = next_cursor

            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code != 200:
                raise Exception(
                    f"Error fetching page content: {response.status_code}, {response.text}"
                )

            data = response.json()
            all_blocks.append(data)
            next_cursor = data.get("next_cursor")
            has_more = data.get("has_more", False)

        return all_blocks

    def count_bullet_points_and_keywords(self, all_content, keywords):
        bullet_count = 0
        keyword_count = 0

        for content in all_content:
            for block in content["results"]:
                if block["type"] == "bulleted_list_item":
                    bullet_count += 1

            for keyword in keywords:
                keyword_count += json.dumps(content).lower().count(keyword)

        return int(bullet_count), int(keyword_count / 2)

    def update_page_title(self, page_id, new_title):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        data = {"properties": {"title": [{"text": {"content": new_title}}]}}
        response = requests.patch(url, json=data, headers=self.headers)
        if response.status_code != 200:
            raise Exception(
                f"Error updating page title: {response.status_code}, {response.text}"
            )

    def do_counts(self, keyword, page_id, dry_run=False):
        content = self.get_page_blocks(page_id)
        bullet_count, keyword_count = self.count_bullet_points_and_keywords(
            content, ["\\u23f0"]
        )  # ⏰
        new_title = f"{keyword_count} - {bullet_count} - {keyword}"
        if not dry_run:
            self.update_page_title(page_id, new_title)
        return True, bullet_count, keyword_count
