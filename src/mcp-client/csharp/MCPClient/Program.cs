using Azure;
using Azure.AI.OpenAI;
using MCPClient;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol.Transport;
using System.Text.Json;

Console.WriteLine("===== Starting up the MCP Client =====");

Console.WriteLine("Loading Environment Variables...");

var root = Directory.GetCurrentDirectory();
// We expect the shared .env to live at the project root, so
// relative path from this "current directory":
//   {project-root}/src/mcp-client/csharp/MCPClient
var dotenv = Path.Combine(root, "../../../../.env");
DotEnv.Load(dotenv);

Console.WriteLine("Setting up logging...");

using var loggerFactory = LoggerFactory.Create(builder =>
    builder.AddConsole().SetMinimumLevel(LogLevel.Information));

Console.WriteLine("Configuring MCP client options and server config...");

var clientOptions = new McpClientOptions
{
    ClientInfo = new() { Name = "local-csharp-client", Version = "0.0.1" }
};
var serverConfig = new McpServerConfig
{
    Id = "fetch",
    Name = "fetch",
    TransportType = TransportTypes.StdIo,
    TransportOptions = new Dictionary<string, string>
    {
        ["command"] = "uv",
        ["arguments"] = @"run ../../../mcp-servers/browser/python/browser_tool"
    }
};

// var serverConfig = new McpServerConfig
// {
//     Id = "mcp-zoning-regulations-fetcher",
//     Name = "mcp-zoning-regulations-fetcher",
//     TransportType = TransportTypes.StdIo,
//     TransportOptions = new Dictionary<string, string>
//     {
//         ["command"] = "uv",
//         ["arguments"] = "run browser_tool"
//     }
// };

// var clientTransport = new StdioClientTransport(new()
// {
//     Command = "uv",
//     Arguments = "run browser_tool"
// }, serverConfig, loggerFactory);

Console.WriteLine("Creating the MCP Client...");

await using var mcpClient =
    await McpClientFactory.CreateAsync(serverConfig, clientOptions, loggerFactory: loggerFactory);

var config = new ConfigurationBuilder()
    .AddUserSecrets<Program>()
    .AddEnvironmentVariables()
    .Build();
string model = config["AZURE_OPENAI_MODEL_NAME"] ?? throw new ArgumentException("AZURE_OPENAI_MODEL_NAME is not set.");
string key = config["AZURE_OPENAI_KEY"] ?? throw new ArgumentException("AZURE_OPENAI_KEY is not set.");
string endpoint = config["AZURE_OPENAI_ENDPOINT"] ?? throw new ArgumentException("AZURE_OPENAI_ENDPOINT is not set.");
var azureOpenAiClient = new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(key))
    .AsChatClient(model);

Console.WriteLine("Listing the MCP servers and tools...");

var mcpTools = await mcpClient.ListToolsAsync();
var toolsJson = JsonSerializer.Serialize(mcpTools, new JsonSerializerOptions { WriteIndented = true });
Console.WriteLine("\nAvailable Tools:\n" + toolsJson);

await Task.Delay(100);

Console.WriteLine("===== MCP Client is ready! =====");
Console.WriteLine("");
Console.WriteLine("Type your message below (or 'exit' to quit):");

List<ChatMessage> chatHistory = new()
{
    new(ChatRole.System, """
        You are a friendly assistant who helps people answer questions about building or adding
        to residences.
        When helping people out, you always ask for this information to inform the answers
        you provide:

        1. The location (city and state) where they would like to build
        2. If it will be new construction or an addition

        If you do not have information specific to the location they've provided, you will
        need to use your tools to find the local website with their specific zoning regulations.
        Download those regulations. Ingest those regulations into your system, and answer based
        on the location-specific information.

        NEVER ANSWER A QUESTION WITHOUT HAVING THE SOURCE INFORMATION FROM THE LOCATION!

        If you don't know the answer or cannot find the location's zoning rules or regulations,
        just respond with that and see if there's anything else you might be able to help with.
    """),
};

while(true)
{
    // Get the user prompt/input and add to chat history

    Console.WriteLine("Request ==> ");
    var userInput = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(userInput))
        continue;

    if (userInput.Trim().Equals("exit", StringComparison.CurrentCultureIgnoreCase))
    {
        Console.WriteLine("Exiting chat...");
        break;
    }

    chatHistory.Add(new ChatMessage(ChatRole.User, userInput));

    // Stream the AI response and add to chat history

    // Console.WriteLine("Response <== ");
    // var response = "";
    // var chatOptions = new ChatOptions { Tools = [.. mcpTools] };
    // await foreach (var item in azureOpenAiClient.GetStreamingResponseAsync(chatHistory, chatOptions))
    // {
    //     Console.Write(item.Text);
    //     response += item.Text;
    // }
    // chatHistory.Add(new ChatMessage(ChatRole.Assistant, response));
    // Console.WriteLine();

    // Just gonna wait... blaming streaming for now.
    try {
        Console.WriteLine("Response <== ");
        var chatOptions = new ChatOptions { Tools = [.. mcpTools], ToolMode = ChatToolMode.Auto };
        var response = await azureOpenAiClient.GetResponseAsync(chatHistory, chatOptions);
        var fromAssistant = response.Messages.LastOrDefault();
        Console.WriteLine();
        Console.WriteLine("DEBUG: " + response.Messages.Count + " Finish Reason: " + response.FinishReason + " Role: " + response.Messages[0].Role + " Text: " + response.Messages[0].Text);
        chatHistory.Add(fromAssistant);
        Console.WriteLine(fromAssistant.Text);
    } catch (Exception e) {
        Console.Error.WriteLine("UNEXPECTED ERROR: " + e.Message);
    }
}