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

    def _rich_text_to_plain(self, rich_text):
        parts = []
        for rt in rich_text:
            if rt["type"] == "text":
                parts.append(rt["text"]["content"])
            elif rt["type"] == "mention":
                parts.append(rt.get("plain_text", ""))
            else:
                parts.append(rt.get("plain_text", ""))
        return "".join(parts)

    def _safe_rich_text(self, rich_text):
        """Convert rich_text to a form the API accepts on write (strips unsupported mention types)."""
        safe = []
        for rt in rich_text:
            if rt["type"] == "text":
                safe.append(rt)
            elif rt["type"] == "mention":
                mtype = rt.get("mention", {}).get("type", "")
                if mtype in ("user", "date", "page", "database", "template_mention"):
                    safe.append(rt)
                else:
                    # e.g. link_mention — convert to plain text link
                    href = rt.get("href")
                    plain = rt.get("plain_text", href or "")
                    safe.append({
                        "type": "text",
                        "text": {"content": plain, "link": {"url": href} if href else None},
                        "annotations": rt.get("annotations", {}),
                    })
            else:
                safe.append(rt)
        return safe

    def list_blocks(self, page_id, block_type=None):
        """Return a flat list of (block_id, type, plain_text) for all blocks on a page."""
        all_blocks = self.get_page_blocks(page_id)
        results = []
        for page in all_blocks:
            for block in page["results"]:
                btype = block["type"]
                if block_type and btype != block_type:
                    continue
                bdata = block.get(btype, {})
                rich_text = bdata.get("rich_text", [])
                plain = self._rich_text_to_plain(rich_text)
                results.append((block["id"], btype, plain))
        return results

    def list_subpages(self, page_id):
        """Return a list of (page_id, title) for all sub-pages referenced from a page."""
        all_blocks = self.get_page_blocks(page_id)
        results = []
        seen = set()
        for page in all_blocks:
            for block in page["results"]:
                btype = block["type"]
                # child_page blocks
                if btype == "child_page":
                    pid = block["id"]
                    title = block.get("child_page", {}).get("title", "")
                    if pid not in seen:
                        results.append((pid, title))
                        seen.add(pid)
                # mention blocks in rich_text
                bdata = block.get(btype, {})
                for rt in bdata.get("rich_text", []):
                    if rt.get("type") == "mention":
                        mention = rt.get("mention", {})
                        if mention.get("type") == "page":
                            pid = mention["page"]["id"]
                            title = rt.get("plain_text", "")
                            if pid not in seen:
                                results.append((pid, title))
                                seen.add(pid)
        return results

    def _build_block_with_children(self, block):
        """Recursively build a block payload including any nested children."""
        btype = block["type"]
        bdata = dict(block[btype])
        if "rich_text" in bdata:
            bdata["rich_text"] = self._safe_rich_text(bdata["rich_text"])
        if block.get("has_children"):
            children_resp = requests.get(
                f"https://api.notion.com/v1/blocks/{block['id']}/children",
                headers=self.headers,
            )
            if children_resp.status_code != 200:
                raise Exception(f"Error fetching children: {children_resp.status_code}, {children_resp.text}")
            children = children_resp.json().get("results", [])
            bdata["children"] = [self._build_block_with_children(c) for c in children]
        return {"object": "block", "type": btype, btype: bdata}

    def move_block(self, block_id, dest_page_id):
        """Move a block to a destination page (append then delete), preserving nested children."""
        url = f"https://api.notion.com/v1/blocks/{block_id}"
        r = requests.get(url, headers=self.headers)
        if r.status_code != 200:
            raise Exception(f"Error fetching block: {r.status_code}, {r.text}")
        new_block = self._build_block_with_children(r.json())
        append_url = f"https://api.notion.com/v1/blocks/{dest_page_id}/children"
        ar = requests.patch(append_url, json={"children": [new_block]}, headers=self.headers)
        if ar.status_code != 200:
            raise Exception(f"Error appending block: {ar.status_code}, {ar.text}")
        dr = requests.delete(url, headers=self.headers)
        if dr.status_code != 200:
            raise Exception(f"Error deleting block: {dr.status_code}, {dr.text}")

    def create_subpage(self, parent_page_id, title):
        """Create a new child page under parent_page_id and return its page_id."""
        url = "https://api.notion.com/v1/pages"
        data = {
            "parent": {"page_id": parent_page_id},
            "properties": {"title": [{"type": "text", "text": {"content": title}}]},
        }
        r = requests.post(url, json=data, headers=self.headers)
        if r.status_code != 200:
            raise Exception(f"Error creating subpage: {r.status_code}, {r.text}")
        return r.json()["id"]

    def do_counts(self, keyword, page_id, dry_run=False):
        content = self.get_page_blocks(page_id)
        bullet_count, keyword_count = self.count_bullet_points_and_keywords(
            content, ["\\u23f0"]
        )  # ⏰
        new_title = f"{keyword_count} - {bullet_count} - {keyword}"
        if not dry_run:
            self.update_page_title(page_id, new_title)
        return True, bullet_count, keyword_count
