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
    try:
        ctx.obj = NotionTools.from_file(token_file)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)


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
    try:
        ctx.obj.append_blocks(page_id, text)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)


@cli.command()
@click.pass_context
@click.argument("page_id", type=str)
@click.argument("title", type=str)
def set_title(ctx: click.Context, page_id, title):
    """Update the title of a Notion page."""
    try:
        ctx.obj.update_page_title(page_id, title)
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
    try:
        _, bullet_count, action_count = ctx.obj.do_counts(keyword, page_id, dry_run)
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
    try:
        blocks = ctx.obj.get_page_blocks(page_id)
    except Exception as e:
        print(f"Program error: {e}")
        exit(1)
    out = json.dumps(blocks, indent=2)
    if output:
        with open(output, "w") as f:
            f.write(out)
    else:
        print(out)


def main():
    cli()


if __name__ == "__main__":
    main()
