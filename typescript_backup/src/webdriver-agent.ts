import { ActionableError, SwipeDirection, ScreenSize, ScreenElement, Orientation } from "./robot";

export interface SourceTreeElementRect {
	x: number;
	y: number;
	width: number;
	height: number;
}

export interface SourceTreeElement {
	type: string;
	label?: string;
	name?: string;
	value?: string;
	rawIdentifier?: string;
	rect: SourceTreeElementRect;
	isVisible?: string; // "0" or "1"
	children?: Array<SourceTreeElement>;
}

export interface SourceTree {
	value: SourceTreeElement;
}

export class WebDriverAgent {

	constructor(private readonly host: string, private readonly port: number) {
	}

	public async isRunning(): Promise<boolean> {
		const url = `http://${this.host}:${this.port}/status`;
		try {
			const response = await fetch(url);
			return response.status === 200;
		} catch (error) {
			console.error(`Failed to connect to WebDriverAgent: ${error}`);
			return false;
		}
	}

	public async createSession(): Promise<string> {
		const url = `http://${this.host}:${this.port}/session`;
		const response = await fetch(url, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify({ capabilities: { alwaysMatch: { platformName: "iOS" } } }),
		});

		const json = await response.json();
		return json.value.sessionId;
	}

	public async deleteSession(sessionId: string) {
		const url = `http://${this.host}:${this.port}/session/${sessionId}`;
		const response = await fetch(url, { method: "DELETE" });
		return response.json();
	}

	public async withinSession(fn: (url: string) => Promise<any>) {
		const sessionId = await this.createSession();
		const url = `http://${this.host}:${this.port}/session/${sessionId}`;
		const result = await fn(url);
		await this.deleteSession(sessionId);
		return result;
	}

	public async getScreenSize(): Promise<ScreenSize> {
		return this.withinSession(async sessionUrl => {
			const url = `${sessionUrl}/wda/screen`;
			const response = await fetch(url);
			const json = await response.json();
			return {
				width: json.value.screenSize.width,
				height: json.value.screenSize.height,
				scale: json.value.scale || 1,
			};
		});
	}

	public async sendKeys(keys: string) {
		await this.withinSession(async sessionUrl => {
			const url = `${sessionUrl}/wda/keys`;
			await fetch(url, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ value: [keys] }),
			});
		});
	}

	public async pressButton(button: string) {
		const _map = {
			"HOME": "home",
			"VOLUME_UP": "volumeup",
			"VOLUME_DOWN": "volumedown",
		};

		if (button === "ENTER") {
			await this.sendKeys("\n");
			return;
		}

		// Type assertion to check if button is a key of _map
		if (!(button in _map)) {
			throw new ActionableError(`Button "${button}" is not supported`);
		}

		await this.withinSession(async sessionUrl => {
			const url = `${sessionUrl}/wda/pressButton`;
			const response = await fetch(url, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({
					name: button,
				}),
			});

			return response.json();
		});
	}

	public async tap(x: number, y: number) {
		await this.withinSession(async sessionUrl => {
			const url = `${sessionUrl}/actions`;
			await fetch(url, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({
					actions: [
						{
							type: "pointer",
							id: "finger1",
							parameters: { pointerType: "touch" },
							actions: [
								{ type: "pointerMove", duration: 0, x, y },
								{ type: "pointerDown", button: 0 },
								{ type: "pause", duration: 100 },
								{ type: "pointerUp", button: 0 }
							]
						}
					]
				}),
			});
		});
	}

	private isVisible(rect: SourceTreeElementRect): boolean {
		return rect.x >= 0 && rect.y >= 0;
	}

	private filterSourceElements(source: SourceTreeElement): Array<ScreenElement> {
		const output: ScreenElement[] = [];

		const acceptedTypes = ["TextField", "Button", "Switch", "Icon", "SearchField", "StaticText", "Image"];

		if (acceptedTypes.includes(source.type)) {
			if (source.isVisible === "1" && this.isVisible(source.rect)) {
				if (source.label !== null || source.name !== null || source.rawIdentifier !== null) {
					output.push({
						type: source.type,
						label: source.label,
						name: source.name,
						value: source.value,
						identifier: source.rawIdentifier,
						rect: {
							x: source.rect.x,
							y: source.rect.y,
							width: source.rect.width,
							height: source.rect.height,
						},
					});
				}
			}
		}

		if (source.children) {
			for (const child of source.children) {
				output.push(...this.filterSourceElements(child));
			}
		}

		return output;
	}

	public async getPageSource(): Promise<SourceTree> {
		const url = `http://${this.host}:${this.port}/source/?format=json`;
		const response = await fetch(url);
		const json = await response.json();
		return json as SourceTree;
	}

	public async getElementsOnScreen(): Promise<ScreenElement[]> {
		const source = await this.getPageSource();
		return this.filterSourceElements(source.value);
	}

	public async openUrl(url: string): Promise<void> {
		await this.withinSession(async sessionUrl => {
			await fetch(`${sessionUrl}/url`, {
				method: "POST",
				body: JSON.stringify({ url }),
			});
		});
	}

        public async swipe(direction: SwipeDirection) {
                const screenSize = await this.getScreenSize();
                await this.withinSession(async sessionUrl => {

                        let x0: number, y0: number, x1: number, y1: number;
                        const centerX = screenSize.width >> 1;
                        const centerY = screenSize.height >> 1;

                        switch (direction) {
                                case "up":
                                        x0 = x1 = centerX;
                                        y0 = Math.floor(screenSize.height * 0.80);
                                        y1 = Math.floor(screenSize.height * 0.20);
                                        break;
                                case "down":
                                        x0 = x1 = centerX;
                                        y0 = Math.floor(screenSize.height * 0.20);
                                        y1 = Math.floor(screenSize.height * 0.80);
                                        break;
                                case "left":
                                        y0 = y1 = centerY;
                                        x0 = Math.floor(screenSize.width * 0.80);
                                        x1 = Math.floor(screenSize.width * 0.20);
                                        break;
                                case "right":
                                        y0 = y1 = centerY;
                                        x0 = Math.floor(screenSize.width * 0.20);
                                        x1 = Math.floor(screenSize.width * 0.80);
                                        break;
                                default:
                                        throw new ActionableError(`Swipe direction "${direction}" is not supported`);
                        }

			const url = `${sessionUrl}/actions`;
			await fetch(url, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({
					actions: [
						{
							type: "pointer",
							id: "finger1",
							parameters: { pointerType: "touch" },
							actions: [
								{ type: "pointerMove", duration: 0, x: x0, y: y0 },
								{ type: "pointerDown", button: 0 },
								{ type: "pointerMove", duration: 0, x: x1, y: y1 },
								{ type: "pause", duration: 1000 },
								{ type: "pointerUp", button: 0 }
							]
						}
					]
				}),
			});
                });
        }

        public async swipeBetweenPoints(startX: number, startY: number, endX: number, endY: number) {
                await this.withinSession(async sessionUrl => {
                        const url = `${sessionUrl}/actions`;
                        await fetch(url, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                        actions: [
                                                {
                                                        type: "pointer",
                                                        id: "finger1",
                                                        parameters: { pointerType: "touch" },
                                                        actions: [
                                                                { type: "pointerMove", duration: 0, x: startX, y: startY },
                                                                { type: "pointerDown", button: 0 },
                                                                { type: "pointerMove", duration: 0, x: endX, y: endY },
                                                                { type: "pause", duration: 1000 },
                                                                { type: "pointerUp", button: 0 }
                                                        ]
                                                }
                                        ]
                                })
                        });
                });
        }

	public async setOrientation(orientation: Orientation): Promise<void> {
		await this.withinSession(async sessionUrl => {
			const url = `${sessionUrl}/orientation`;
			await fetch(url, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					orientation: orientation.toUpperCase()
				})
			});
		});
	}

	public async getOrientation(): Promise<Orientation> {
		return this.withinSession(async sessionUrl => {
			const url = `${sessionUrl}/orientation`;
			const response = await fetch(url);
			const json = await response.json();
			return json.value.toLowerCase() as Orientation;
		});
	}
}
