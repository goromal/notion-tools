import click
import json

from notion_tools.defaults import NotionToolsDefaults as NTD
from notion_tools.manage import NotionTools


class NotRequiredIf(click.Option):
    def __init__(self, *args, **kwargs):
        self.not_required_if = kwargs.pop("not_required_if")
        assert self.not_required_if, "'not_required_if' parameter required"
        kwargs["help"] = (
            kwargs.get("help", "")
            + " NOTE: This argument is mutually exclusive with %s" % self.not_required_if
        ).strip()
        super(NotRequiredIf, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        we_are_present = self.name in opts
        other_present = self.not_required_if in opts
        if other_present:
            if we_are_present:
                raise click.UsageError(
                    "Illegal usage: `%s` is mutually exclusive with `%s`"
                    % (self.name, self.not_required_if)
                )
            else:
                self.prompt = None
        return super(NotRequiredIf, self).handle_parse_result(ctx, opts, args)


def _get_notion(ctx):
    try:
        return NotionTools.from_file(ctx.obj)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)


@click.group()
@click.pass_context
@click.option(
    "--token-file",
    "token_file",
    type=click.Path(),
    default=NTD.NOTION_TOKEN_FILE,
    show_default=True,
    help="Notion API token secrets file.",
)
def cli(ctx: click.Context, token_file):
    """Interact with Notion pages."""
    ctx.obj = token_file


@cli.command()
@click.pass_context
@click.argument("page_id", type=str)
@click.option(
    "--file",
    "content_file",
    type=click.Path(exists=True),
    required=False,
    help="File containing text to append.",
)
@click.option(
    "--content",
    "content",
    type=str,
    cls=NotRequiredIf,
    not_required_if="content_file",
    help="Text to append if --file is not specified.",
)
def append(ctx: click.Context, page_id, content_file, content):
    """Append text as a bulleted list to a Notion page."""
    if content_file is not None:
        with open(content_file, "r") as f:
            text = f.read()
    elif content is not None:
        text = content
    else:
        print("ERROR: provide --file or --content")
        exit(1)
    notion = _get_notion(ctx)
    try:
        notion.append_blocks(page_id, text)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)


@cli.command()
@click.pass_context
@click.argument("page_id", type=str)
@click.argument("title", type=str)
def set_title(ctx: click.Context, page_id, title):
    """Update the title of a Notion page."""
    notion = _get_notion(ctx)
    try:
        notion.update_page_title(page_id, title)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)


@cli.command()
@click.pass_context
@click.argument("keyword", type=str)
@click.argument("page_id", type=str)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="Count but don't update the page title.",
)
def annotate(ctx: click.Context, keyword, page_id, dry_run):
    """Count bullets and action items on a page and retitle it with the counts."""
    notion = _get_notion(ctx)
    try:
        _, bullet_count, action_count = notion.do_counts(keyword, page_id, dry_run)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)
    print(f"{keyword}: {bullet_count} bullets, {action_count} action items")


@cli.command()
@click.pass_context
@click.argument("page_id", type=str)
@click.option(
    "--output",
    "output",
    type=str,
    default="",
    show_default=True,
    help="Output file path. Prints to stdout if not specified.",
)
def get_blocks(ctx: click.Context, page_id, output):
    """Fetch the block content of a Notion page as JSON."""
    notion = _get_notion(ctx)
    try:
        blocks = notion.get_page_blocks(page_id)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)
    out = json.dumps(blocks, indent=2)
    if output:
        with open(output, "w") as f:
            f.write(out)
    else:
        print(out)


@cli.command()
@click.pass_context
@click.argument("page_id", type=str)
@click.option(
    "--type",
    "block_type",
    type=str,
    default="",
    help="Filter by block type (e.g. bulleted_list_item).",
)
def list_blocks(ctx: click.Context, page_id, block_type):
    """List blocks on a page as tab-separated block_id, type, text."""
    notion = _get_notion(ctx)
    try:
        blocks = notion.list_blocks(page_id, block_type or None)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)
    for block_id, btype, text in blocks:
        print(f"{block_id}\t{btype}\t{text}")


@cli.command()
@click.pass_context
@click.argument("page_id", type=str)
def list_subpages(ctx: click.Context, page_id):
    """List sub-pages referenced from a page as tab-separated page_id, title."""
    notion = _get_notion(ctx)
    try:
        subpages = notion.list_subpages(page_id)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)
    for pid, title in subpages:
        print(f"{pid}\t{title}")


@cli.command()
@click.pass_context
@click.argument("parent_page_id", type=str)
@click.argument("title", type=str)
def create_subpage(ctx: click.Context, parent_page_id, title):
    """Create a new child page under a parent page and print its page_id."""
    notion = _get_notion(ctx)
    try:
        page_id = notion.create_subpage(parent_page_id, title)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)
    print(page_id)


@cli.command()
@click.pass_context
@click.argument("block_id", type=str)
@click.argument("dest_page_id", type=str)
def move_block(ctx: click.Context, block_id, dest_page_id):
    """Move a block from its current page to a destination page."""
    notion = _get_notion(ctx)
    try:
        notion.move_block(block_id, dest_page_id)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
