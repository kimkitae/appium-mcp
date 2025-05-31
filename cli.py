import asyncio
import click
import json
import os

from app import (
    auto_setup,
    list_available_devices,
    check_connection_status,
    restart_connection,
    connect,
    disconnect,
    current_device_info,
    screenshot,
    screen_analysis,
    click_coordinates,
    click as click_element,
    swipe,
    is_displayed,
    get_attribute,
    activate_app,
    get_page_source,
    long_press,
)

JSON_ENV = os.environ.get("MCP_JSON", "0").lower() in ("1", "true")


def output_result(result, json_output: bool):
    if json_output:
        if not isinstance(result, (dict, list)):
            result = {"result": result}
        click.echo(json.dumps(result, ensure_ascii=False))
    else:
        if isinstance(result, (dict, list)):
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            click.echo(result)


@click.group()
@click.option("--json", "json_output", is_flag=True, help="Return output in JSON format")
@click.pass_context
def cli(ctx, json_output):
    """Appium MCP CLI."""
    ctx.obj = {"json": json_output or JSON_ENV}


def run_async(coro):
    return asyncio.run(coro)


@cli.command(name="auto-setup")
@click.pass_obj
def auto_setup_cmd(obj):
    """Start Appium server and auto connect to a device."""
    result = run_async(auto_setup())
    output_result(result, obj["json"])


@cli.command(name="list-devices")
def list_devices_cmd():
    """List available devices."""
    result = run_async(list_available_devices())
    click.echo(result)


@cli.command()
@click.pass_obj
def status(obj):
    """Check current connection status."""
    result = run_async(check_connection_status())
    output_result(result, obj["json"])


@cli.command()
@click.pass_obj
def restart(obj):
    """Restart connection."""
    result = run_async(restart_connection())
    output_result(result, obj["json"])


@cli.command()
@click.argument("platform")
@click.option("--udid", default="", help="Device UDID/serial number")
@click.option("--device-name", default="", help="Device name")
@click.option("--app-package", default="", help="Android app package")
@click.option("--app-activity", default="", help="Android app activity")
@click.option("--bundle-id", default="", help="iOS bundle identifier")
@click.pass_obj
def connect_device(obj, platform, udid, device_name, app_package, app_activity, bundle_id):
    """Connect to a device."""
    result = run_async(
        connect(
            platform=platform,
            deviceName=device_name,
            udid=udid,
            appPackage=app_package,
            appActivity=app_activity,
            bundleId=bundle_id,
        )
    )
    output_result(result, obj["json"])


@cli.command(name="disconnect")
@click.pass_obj
def disconnect_device(obj):
    """Disconnect the current device."""
    result = run_async(disconnect())
    output_result(result, obj["json"])


@cli.command(name="current-device")
@click.pass_obj
def current_device_cmd(obj):
    """Show info about the current device."""
    result = run_async(current_device_info())
    output_result(result, obj["json"])


@cli.command()
@click.pass_obj
def screenshot_cmd(obj):
    """Take a screenshot and output base64."""
    result = run_async(screenshot())
    output_result(result, obj["json"])


@cli.command(name="screen-analysis")
@click.option("--detailed", is_flag=True, help="Use detailed mode for page source")
@click.pass_obj
def screen_analysis_cmd(obj, detailed):
    """Return screenshot and page source."""
    result = run_async(screen_analysis(detailed=detailed))
    output_result(result, obj["json"])


@cli.command(name="click-coord")
@click.argument("x", type=int)
@click.argument("y", type=int)
@click.pass_obj
def click_coord(obj, x, y):
    """Click specific coordinates."""
    result = run_async(click_coordinates(x, y))
    output_result(result, obj["json"])


@cli.command(name="click")
@click.argument("by")
@click.argument("value")
@click.pass_obj
def click_elem(obj, by, value):
    """Click element by locator."""
    result = run_async(click_element(by, value))
    output_result(result, obj["json"])


@cli.command()
@click.argument("start_x", type=int)
@click.argument("start_y", type=int)
@click.argument("end_x", type=int)
@click.argument("end_y", type=int)
@click.option("--duration", default=800, type=int, help="Swipe duration in ms")
@click.pass_obj
def swipe_cmd(obj, start_x, start_y, end_x, end_y, duration):
    """Swipe from coordinates."""
    result = run_async(swipe(start_x, start_y, end_x, end_y, duration))
    output_result(result, obj["json"])


@cli.command(name="is-displayed")
@click.argument("by")
@click.argument("value")
@click.pass_obj
def is_displayed_cmd(obj, by, value):
    """Check if element is displayed."""
    result = run_async(is_displayed(by, value))
    output_result(result, obj["json"])


@cli.command(name="get-attribute")
@click.argument("by")
@click.argument("value")
@click.argument("attribute")
@click.pass_obj
def get_attribute_cmd(obj, by, value, attribute):
    """Get element attribute."""
    result = run_async(get_attribute(by, value, attribute))
    output_result(result, obj["json"])


@cli.command(name="activate-app")
@click.argument("app_id", default="")
@click.pass_obj
def activate_app_cmd(obj, app_id):
    """Activate an app by bundle/package id."""
    result = run_async(activate_app(app_id))
    output_result(result, obj["json"])


@cli.command(name="page-source")
@click.option("--detailed", is_flag=True, help="Use detailed mode for page source")
@click.pass_obj
def page_source_cmd(obj, detailed):
    """Get page source."""
    result = run_async(get_page_source(detailed=detailed))
    output_result(result, obj["json"])


@cli.command(name="long-press")
@click.argument("by")
@click.argument("value")
@click.option("--duration", default=2000, type=int, help="Press duration in ms")
@click.pass_obj
def long_press_cmd(obj, by, value, duration):
    """Long press element."""
    result = run_async(long_press(by, value, duration))
    output_result(result, obj["json"])


if __name__ == "__main__":
    cli()
