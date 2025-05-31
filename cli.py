import asyncio
import click

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

@click.group()
def cli():
    """Appium MCP CLI."""
    pass


def run_async(coro):
    return asyncio.run(coro)


@cli.command(name="auto-setup")
def auto_setup_cmd():
    """Start Appium server and auto connect to a device."""
    result = run_async(auto_setup())
    click.echo(result)


@cli.command(name="list-devices")
def list_devices_cmd():
    """List available devices."""
    result = run_async(list_available_devices())
    click.echo(result)


@cli.command()
def status():
    """Check current connection status."""
    result = run_async(check_connection_status())
    click.echo(result)


@cli.command()
def restart():
    """Restart connection."""
    result = run_async(restart_connection())
    click.echo(result)


@cli.command()
@click.argument("platform")
@click.option("--udid", default="", help="Device UDID/serial number")
@click.option("--device-name", default="", help="Device name")
@click.option("--app-package", default="", help="Android app package")
@click.option("--app-activity", default="", help="Android app activity")
@click.option("--bundle-id", default="", help="iOS bundle identifier")
def connect_device(platform, udid, device_name, app_package, app_activity, bundle_id):
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
    click.echo(result)


@cli.command(name="disconnect")
def disconnect_device():
    """Disconnect the current device."""
    result = run_async(disconnect())
    click.echo(result)


@cli.command(name="current-device")
def current_device_cmd():
    """Show info about the current device."""
    result = run_async(current_device_info())
    click.echo(result)


@cli.command()
def screenshot_cmd():
    """Take a screenshot and output base64."""
    result = run_async(screenshot())
    click.echo(result)


@cli.command(name="screen-analysis")
@click.option("--detailed", is_flag=True, help="Use detailed mode for page source")
def screen_analysis_cmd(detailed):
    """Return screenshot and page source."""
    result = run_async(screen_analysis(detailed=detailed))
    click.echo(result)


@cli.command(name="click-coord")
@click.argument("x", type=int)
@click.argument("y", type=int)
def click_coord(x, y):
    """Click specific coordinates."""
    result = run_async(click_coordinates(x, y))
    click.echo(result)


@cli.command(name="click")
@click.argument("by")
@click.argument("value")
def click_elem(by, value):
    """Click element by locator."""
    result = run_async(click_element(by, value))
    click.echo(result)


@cli.command()
@click.argument("start_x", type=int)
@click.argument("start_y", type=int)
@click.argument("end_x", type=int)
@click.argument("end_y", type=int)
@click.option("--duration", default=800, type=int, help="Swipe duration in ms")
def swipe_cmd(start_x, start_y, end_x, end_y, duration):
    """Swipe from coordinates."""
    result = run_async(swipe(start_x, start_y, end_x, end_y, duration))
    click.echo(result)


@cli.command(name="is-displayed")
@click.argument("by")
@click.argument("value")
def is_displayed_cmd(by, value):
    """Check if element is displayed."""
    result = run_async(is_displayed(by, value))
    click.echo(result)


@cli.command(name="get-attribute")
@click.argument("by")
@click.argument("value")
@click.argument("attribute")
def get_attribute_cmd(by, value, attribute):
    """Get element attribute."""
    result = run_async(get_attribute(by, value, attribute))
    click.echo(result)


@cli.command(name="activate-app")
@click.argument("app_id", default="")
def activate_app_cmd(app_id):
    """Activate an app by bundle/package id."""
    result = run_async(activate_app(app_id))
    click.echo(result)


@cli.command(name="page-source")
@click.option("--detailed", is_flag=True, help="Use detailed mode for page source")
def page_source_cmd(detailed):
    """Get page source."""
    result = run_async(get_page_source(detailed=detailed))
    click.echo(result)


@cli.command(name="long-press")
@click.argument("by")
@click.argument("value")
@click.option("--duration", default=2000, type=int, help="Press duration in ms")
def long_press_cmd(by, value, duration):
    """Long press element."""
    result = run_async(long_press(by, value, duration))
    click.echo(result)


if __name__ == "__main__":
    cli()
