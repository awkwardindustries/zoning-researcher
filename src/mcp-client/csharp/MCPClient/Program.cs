using Azure;
using Azure.AI.OpenAI;
using MCPClient;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol.Transport;
using System.Text.Json;

Console.WriteLine("===== Starting up the MCP Client =====");

Console.WriteLine("\nLoading Environment Variables...");

var root = Directory.GetCurrentDirectory();
var dotenv = Path.Combine("../../../../.env");
DotEnv.Load(dotenv);

Console.WriteLine("\nSetting up logging...");

using var loggerFactory = LoggerFactory.Create(builder =>
    builder.AddConsole().SetMinimumLevel(LogLevel.Information));

Console.WriteLine("\nCreating the MCP Client...");

IClientTransport clientTransport = new SseClientTransport(transportOptions: new()
    {
        Endpoint = new Uri("http://localhost:8080/sse")
    }, 
    loggerFactory: loggerFactory);
await using var mcpClient = await McpClientFactory.CreateAsync(clientTransport, loggerFactory: loggerFactory);

Console.WriteLine("\nCreating the Chat Client...");

var config = new ConfigurationBuilder()
    .AddUserSecrets<Program>()
    .AddEnvironmentVariables()
    .Build();
string model = config["AZURE_OPENAI_MODEL_NAME"] ?? throw new ArgumentException("AZURE_OPENAI_MODEL_NAME is not set.");
string key = config["AZURE_OPENAI_KEY"] ?? throw new ArgumentException("AZURE_OPENAI_KEY is not set.");
string endpoint = config["AZURE_OPENAI_ENDPOINT"] ?? throw new ArgumentException("AZURE_OPENAI_ENDPOINT is not set.");

using IChatClient chatClient = 
    new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(key)).AsChatClient(model)
    .AsBuilder()
    .UseFunctionInvocation()
    .Build();

Console.WriteLine("\nListing the MCP servers and tools...");

var mcpTools = await mcpClient.ListToolsAsync();
var toolsJson = JsonSerializer.Serialize(mcpTools, options: new(){ WriteIndented = true });
Console.WriteLine("\nAvailable Tools:\n" + toolsJson);

await Task.Delay(100);

Console.WriteLine("\n===== MCP Client is ready! =====\n");
Console.WriteLine("Type your message below (or 'exit' to quit):");

List<ChatMessage> chatHistory =
[
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
];

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

    Console.WriteLine("Response <== ");
    
    List<ChatResponseUpdate> updates = [];
    await foreach (var update in chatClient.GetStreamingResponseAsync(chatHistory, new() { Tools = [.. mcpTools]}))
    {
        Console.Write(update);
        updates.Add(update);
    }
    Console.WriteLine();

    chatHistory.AddMessages(updates);

}