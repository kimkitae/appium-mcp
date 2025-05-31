#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createMcpServer } from "./server";
import { error } from "./logger";

async function main() {
	const transport = new StdioServerTransport();

	const server = createMcpServer();
	await server.connect(transport);

	error("mobile-mcp server running on stdio");
}

main().catch(err => {
	console.error("Fatal error in main():", err);
	error("Fatal error in main(): " + JSON.stringify(err.stack));
	process.exit(1);
});
