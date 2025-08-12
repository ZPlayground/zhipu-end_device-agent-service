<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

1. Whenever you write anything about the A2A protocol, please ensure to reference the latest version of the protocol documentation. The most up-to-date version of the A2A protocol can be found in the `docs/a2a_protocol.md` file. And the `a2a-sdk` package is the official SDK for A2A protocol implementation. You should not try to implement the A2A protocol from scratch, but rather use the official SDK for any A2A-related tasks.

2. Do not repeat the same information or code snippets that have already been provided in the context or any files in the project folder. Always check the context for existing information before suggesting new content.

3. Configuration information should be centrally managed. Use `config/` for all configuration files, and ensure that any new configuration settings are added to the appropriate configuration file in this directory. Configuration management utils should be written in `src/config/` and should not be duplicated across different files.

4. Don't hard code anything. Use configuration files or environment variables to manage settings and secrets.

5. Whenever you write a test script, ensure that there is no previous scripts that already covers the same functionality. If a test script already exists, you should enhance it instead of creating a new one. Always delete any redundant test scripts to keep the project clean and maintainable.

6. If you write any code that interacts with the MCP, consider `https://github.com/modelcontextprotocol/python-sdk` and `https://modelcontextprotocol.io/docs/learn/client-concepts` as a reference for best practices and implementation details.