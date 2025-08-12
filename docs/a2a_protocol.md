好的，这是根据您提供的HTML文件整理的A2A协议规范的Markdown格式内容。

-----

# Agent2Agent (A2A) 协议规范

**版本:** `dev`

查看 [发布说明](https://github.com/a2aproject/A2A/releases) 以了解版本之间的变更。

## 1\. 简介

Agent2Agent (A2A) 协议是一个开放标准，旨在促进独立、可能不透明的AI代理系统之间的通信和互操作性。在一个代理可能使用不同框架、语言或由不同供应商构建的生态系统中，A2A提供了一种通用的语言和交互模型。

本文档提供了A2A协议的详细技术规范。其主要目标是使代理能够：

  * 发现彼此的能力。
  * 协商交互方式（文本、文件、结构化数据）。
  * 管理协作任务。
  * 安全地交换信息以实现用户目标，**而无需访问彼此的内部状态、内存或工具。**

### 1.1. A2A 的主要目标

  * **互操作性:** 弥合不同代理系统之间的通信鸿沟。
  * **协作:** 使代理能够委派任务、交换上下文，并共同处理复杂的用户请求。
  * **发现:** 允许代理动态地找到并理解其他代理的能力。
  * **灵活性:** 支持各种交互模式，包括同步请求/响应、用于实时更新的流式传输，以及用于长时间运行任务的异步推送通知。
  * **安全性:** 促进适用于企业环境的安全通信模式，依赖于标准的Web安全实践。
  * **异步性:** 原生支持长时间运行的任务和可能涉及“人在环路”场景的交互。

### 1.2. 指导原则

  * **简单:** 重用现有的、易于理解的标准（HTTP、JSON-RPC 2.0、服务器发送事件）。
  * **企业就绪:** 通过与既定的企业实践保持一致，解决认证、授权、安全、隐私、追踪和监控问题。
  * **异步优先:** 为（可能非常）长时间运行的任务和“人在环路”的交互而设计。
  * **模式无关:** 支持交换多种内容类型，包括文本、音视频（通过文件引用）、结构化数据/表单，以及潜在的嵌入式UI组件（例如，在部件中引用的iframe）。
  * **不透明执行:** 代理基于声明的能力和交换的信息进行协作，无需共享其内部思想、计划或工具实现。

要更广泛地了解A2A的目的和好处，请参阅[什么是A2A？](https://a2a-protocol.org/latest/topics/what-is-a2a/)。

## 2\. 核心概念摘要

A2A围绕几个关键概念展开。有关详细解释，请参阅[关键概念指南](https://a2a-protocol.org/latest/topics/key-concepts/)。

  * **A2A客户端:** 代表用户或另一个系统向A2A服务器发起请求的应用程序或代理。
  * **A2A服务器 (远程代理):** 暴露一个符合A2A规范的HTTP端点的代理或代理系统，处理任务并提供响应。
  * **代理卡 (Agent Card):** 由A2A服务器发布的JSON元数据文档，描述其身份、能力、技能、服务端点和认证要求。
  * **消息 (Message):** 客户端和远程代理之间的一个通信回合，具有`role`（“user”或“agent”）并包含一个或多个`Part`。
  * **任务 (Task):** A2A管理的基本工作单元，由唯一ID标识。任务是有状态的，并经历一个定义的生命周期。
  * **部件 (Part):** 消息或工件中的最小内容单元（例如，`TextPart`, `FilePart`, `DataPart`）。
  * **工件 (Artifact):** 代理因任务而生成的输出（例如，文档、图像、结构化数据），由`Parts`组成。
  * **流式传输 (SSE):** 通过服务器发送事件（Server-Sent Events）提供的任务实时、增量更新（状态变化、工件块）。
  * **推送通知 (Push Notifications):** 通过服务器发起的HTTP POST请求，将异步任务更新发送到客户端提供的webhook URL，用于长时间运行或断开连接的场景。
  * **上下文 (Context):** 一个可选的、由服务器生成的标识符，用于逻辑上分组相关的任务。
  * **扩展 (Extension):** 一种机制，允许代理在核心A2A规范之外提供额外的功能或数据。

## 3\. 传输与格式

### 3.1. 传输层要求

A2A支持多种传输协议，所有这些协议都运行在\*\*HTTP(S)\*\*之上。代理可以根据其具体要求和用例灵活选择实现哪种传输协议：

  * A2A通信**必须**通过\*\*HTTP(S)\*\*进行。
  * A2A服务器在其`AgentCard`中定义的一个或多个URL上暴露其服务。
  * 代理**必须**至少实现本规范中定义的三个核心传输协议之一。
  * 所有支持的传输协议在状态和能力上都被认为是平等的。

### 3.2. 支持的传输协议

A2A定义了三个核心传输协议。\*\*符合A2A规范的代理应至少实现其中一种传输协议。它们也可以通过实现3.2.4中定义的传输扩展来保持合规。\*\*所有三种协议在状态上都被认为是平等的，代理可以根据其要求选择实现它们的任意组合。

#### 3.2.1. JSON-RPC 2.0 传输

代理**可以**支持JSON-RPC 2.0传输。如果实现，它**必须**符合以下要求：

  * 所有请求和响应（不包括SSE流包装器）的主要数据格式是\*\*[JSON-RPC 2.0](https://www.jsonrpc.org/specification)\*\*。
  * 客户端请求和服务器响应**必须**遵守JSON-RPC 2.0规范。
  * 包含JSON-RPC有效负载的HTTP请求和响应的`Content-Type`头**必须**是`application/json`。
  * 方法名称遵循`{category}/{action}`的模式（例如，`"message/send"`, `"tasks/get"`）。

#### 3.2.2. gRPC 传输

代理**可以**支持gRPC传输。如果实现，它**必须**符合以下要求：

  * **协议定义**: **必须**使用`specification/grpc/a2a.proto`中的规范性Protocol Buffers定义。
  * **消息序列化**: **必须**使用Protocol Buffers版本3进行消息序列化。
  * **服务定义**: **必须**实现proto文件中定义的`A2AService` gRPC服务。
  * **方法覆盖**: **必须**提供所有与其它支持的传输协议功能等效的方法。
  * **字段映射**: **必须**使用`json_name`注解以兼容HTTP/JSON转码。
  * **错误处理**: **必须**将A2A错误代码映射到proto注解中定义的适当gRPC状态码。
  * **传输安全**: **必须**支持TLS加密（gRPC over HTTP/2 with TLS）。

#### 3.2.3. HTTP+JSON/REST 传输

代理**可以**支持REST风格的HTTP+JSON传输。如果实现，它**必须**符合以下要求：

  * **HTTP方法**: **必须**使用适当的HTTP动词（GET用于查询，POST用于操作，PUT用于更新，DELETE用于删除）。
  * **URL模式**: **必须**遵循每个方法部分中记录的URL模式（例如，`/v1/message:send`, `/v1/tasks/{id}`）。
  * **Content-Type**: **必须**为请求和响应体使用`application/json`。
  * **HTTP状态码**: **必须**使用与A2A错误类型相对应的适当HTTP状态码（200, 400, 401, 403, 404, 500等）。
  * **请求/响应格式**: **必须**使用与核心A2A数据结构在结构上等效的JSON对象。
  * **方法覆盖**: **必须**提供所有与其它支持的传输协议功能等效的方法。
  * **错误格式**: **必须**以一种与A2A错误类型映射的一致JSON格式返回错误响应。

#### 3.2.4. 传输扩展

额外的传输协议**可以**被定义为核心A2A规范的扩展。此类扩展：

  * **必须**保持与核心传输协议的功能等效性。
  * **必须**使用清晰的命名空间标识符以避免冲突。
  * **必须**被清晰地记录和指定。
  * **应该**提供从核心传输协议的迁移路径。

### 3.3. 流式传输 (服务器发送事件)

流式传输能力是**特定于传输协议**的：

#### 3.3.1. JSON-RPC 2.0 流式传输

当流式传输用于像`message/stream`或`tasks/resubscribe`这样的方法时：

  * 服务器以HTTP `200 OK`状态和`Content-Type`为`text/event-stream`的头进行响应。
  * 此HTTP响应的正文包含一个由W3C定义的\*\*[服务器发送事件 (SSE)](https://html.spec.whatwg.org/multipage/server-sent-events.html#server-sent-events)\*\*流。
  * 每个SSE的`data`字段包含一个完整的JSON-RPC 2.0响应对象（具体来说是`SendStreamingMessageResponse`）。

#### 3.3.2. gRPC 流式传输

gRPC传输使用Protocol Buffers规范中定义的**服务器流式RPC**进行流式操作。

#### 3.3.3. HTTP+JSON/REST 流式传输

如果支持REST传输，它**必须**使用类似于JSON-RPC的服务器发送事件来实现流式传输。

### 3.4. 传输合规性与互操作性

#### 3.4.1. 功能等效性要求

当一个代理支持多种传输时，所有支持的传输**必须**：

  * **功能相同**: 提供相同的操作和能力集。
  * **行为一致**: 对相同的请求返回语义上等效的结果。
  * **错误处理相同**: 使用[第8节](https://www.google.com/search?q=%238-error-handling)中定义的错误代码在不同传输中一致地映射错误。
  * **认证等效**: 支持`AgentCard`中声明的相同认证方案。

#### 3.4.2. 传输选择与协商

  * **代理声明**: 代理**必须**在其`AgentCard`中使用`preferredTransport`和`additionalInterfaces`字段声明所有支持的传输。
  * **客户端选择**: 客户端**可以**选择代理声明的任何传输。
  * **无传输协商**: A2A没有定义动态传输协商协议。客户端根据静态的`AgentCard`信息选择传输。
  * **回退行为**: 如果首选传输失败，客户端**应该**实现回退逻辑以尝试其他传输。具体的回退策略取决于实现。

#### 3.4.3. 传输特定扩展

传输**可以**提供不影响功能等效性的传输特定优化或扩展：

  * **gRPC**: 可以利用gRPC特有的功能，如双向流、元数据或自定义状态码。
  * **REST**: 可以提供额外的HTTP缓存头或支持HTTP条件请求。
  * **JSON-RPC**: 可以在不与核心规范冲突的情况下，在JSON-RPC请求/响应对象中包含额外的字段。

此类扩展**必须**是向后兼容的，并且**不得**破坏与不支持这些扩展的客户端的互操作性。

### 3.5. 方法映射与命名约定

为确保不同传输之间的一致性和可预测性，A2A定义了规范性的方法映射规则。

#### 3.5.1. JSON-RPC 方法命名

JSON-RPC方法**必须**遵循以下模式：`{category}/{action}`，其中：

  * `category` 代表资源类型（例如，“message”，“tasks”，“agent”）
  * `action` 代表操作（例如，“send”，“get”，“cancel”）
  * 嵌套操作使用正斜杠（例如，“tasks/pushNotificationConfig/set”）

#### 3.5.2. gRPC 方法命名

gRPC方法**必须**遵循Protocol Buffers服务约定，使用PascalCase：

  * 将JSON-RPC的category/action转换为PascalCase复合词
  * 使用标准的gRPC方法前缀（Get, Set, List, Create, Delete, Cancel）

#### 3.5.3. HTTP+JSON/REST 方法命名

REST端点**必须**遵循RESTful URL模式，并使用适当的HTTP动词：

  * 使用基于资源的URL：`/v1/{resource}[/{id}][:{action}]`
  * 使用与REST语义一致的标准HTTP方法
  * 对非CRUD操作使用冒号表示法

#### 3.5.4. 方法映射合规性

在实现多种传输时，代理**必须**：

  * **使用标准映射**: 遵循3.5.2和3.5.3节中定义的方法映射。
  * **保持功能等效性**: 每个特定于传输的方法**必须**在所有支持的传输中提供相同的功能。
  * **参数一致**: 在不同传输中使用等效的参数结构（考虑到传输特定的序列化差异）。
  * **响应等效**: 对同一操作，在所有传输中返回语义上等效的响应。

#### 3.5.5. 扩展方法命名

对于核心A2A规范中未定义的自定义或扩展方法：

  * **JSON-RPC**: 遵循`{category}/{action}`模式，并使用清晰的命名空间（例如，`myorg.extension/action`）
  * **gRPC**: 使用遵循Protocol Buffers约定的适当服务和方法名称
  * **REST**: 使用清晰的基于资源的URL和适当的HTTP方法

扩展方法**必须**被清晰地记录，并且**不得**与核心A2A方法名称或语义冲突。

#### 3.5.6. 方法映射参考表

为快速参考，下表总结了所有传输的方法映射：

| JSON-RPC 方法                        | gRPC 方法                      | REST 端点                                             | 描述                       |
| ------------------------------------ | ------------------------------ | ----------------------------------------------------- | -------------------------- |
| `message/send`                       | `SendMessage`                  | `POST /v1/message:send`                               | 发送消息给代理             |
| `message/stream`                     | `SendStreamingMessage`         | `POST /v1/message:stream`                             | 带流式传输的消息发送       |
| `tasks/get`                          | `GetTask`                      | `GET /v1/tasks/{id}`                                  | 获取任务状态               |
| `tasks/list`                         | `ListTask`                     | `GET /v1/tasks`                                       | 列出任务（仅限gRPC/REST） |
| `tasks/cancel`                       | `CancelTask`                   | `POST /v1/tasks/{id}:cancel`                          | 取消任务                   |
| `tasks/resubscribe`                  | `TaskSubscription`             | `POST /v1/tasks/{id}:subscribe`                       | 恢复任务流                 |
| `tasks/pushNotificationConfig/set`   | `CreateTaskPushNotification`   | `POST /v1/tasks/{id}/pushNotificationConfigs`         | 设置推送通知配置         |
| `tasks/pushNotificationConfig/get`   | `GetTaskPushNotification`      | `GET /v1/tasks/{id}/pushNotificationConfigs/{configId}` | 获取推送通知配置         |
| `tasks/pushNotificationConfig/list`  | `ListTaskPushNotification`     | `GET /v1/tasks/{id}/pushNotificationConfigs`          | 列出推送通知配置         |
| `tasks/pushNotificationConfig/delete`| `DeleteTaskPushNotification`   | `DELETE /v1/tasks/{id}/pushNotificationConfigs/{configId}`| 删除推送通知配置         |
| `agent/getAuthenticatedExtendedCard` | `GetAgentCard`                 | `GET /v1/card`                                        | 获取认证后的代理卡       |

## 4\. 认证与授权

A2A将代理视为标准的企业应用程序，依赖于已建立的Web安全实践。身份信息**不**在A2A JSON-RPC有效负载内传输；它在HTTP传输层处理。

有关企业安全方面的全面指南，请参阅[企业级功能](https://a2a-protocol.org/latest/topics/enterprise-ready/)。

### 4.1. 传输安全

如3.1节所述，生产部署**必须**使用HTTPS。实现**应该**使用现代的[TLS](https://datatracker.ietf.org/doc/html/rfc8446)配置（推荐TLS 1.3+）和强密码套件。

### 4.2. 服务器身份验证

A2A客户端**应该**通过在TLS握手期间验证其TLS证书与受信任的证书颁发机构（CAs）来验证A2A服务器的身份。

### 4.3. 客户端/用户身份与认证过程

1.  **发现要求：** 客户端通过`AgentCard`中的`authentication`字段发现服务器所需的认证方案。方案名称通常与[OpenAPI认证方法](https://swagger.io/docs/specification/authentication/)对齐（例如，“Bearer”用于OAuth 2.0令牌，“Basic”用于基本认证，“ApiKey”用于API密钥）。
2.  **凭证获取（带外）：** 客户端通过一个**带外过程**获取必要的凭证（例如，API密钥、OAuth令牌、JWTs），该过程特定于所需的认证方案和身份提供商。此过程超出了A2A协议本身的范围。
3.  **凭证传输：** 客户端在发送给服务器的每个A2A请求的适当[HTTP头](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers)中包含这些凭证（例如，`Authorization: Bearer <token>`，`X-API-Key: <value>`）。

### 4.4. 服务器认证责任

A2A服务器：

  * **必须**根据提供的HTTP凭证及其代理卡中声明的认证要求对每个传入请求进行认证。
  * **应该**对认证挑战或拒绝使用标准HTTP状态码，如[`401 Unauthorized`](https://www.google.com/search?q=%5Bhttps://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401)或](https://www.google.com/search?q=https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401)%E6%88%96)[`403 Forbidden`](https://www.google.com/search?q=%5Bhttps://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403%5D\(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403\))。
  * **应该**在`401 Unauthorized`响应中包含相关的HTTP头（例如，[`WWW-Authenticate`](https://www.google.com/search?q=%5Bhttps://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/WWW-Authenticate%5D\(https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/WWW-Authenticate\))），以指示所需的认证方案，从而指导客户端。

### 4.5. 任务内认证（次要凭证）

如果一个代理在执行任务期间，需要用于**不同**系统或资源的**额外**凭证（例如，代表用户访问需要自己认证的特定工具）：

1.  它**应该**将A2A任务转换为`auth-required`状态（参见`TaskState`）。
2.  附带的`TaskStatus.message`（通常是一个`DataPart`）**应该**提供有关所需次要认证的详细信息，可能使用类似`PushNotificationAuthenticationInfo`的结构来描述需求。
3.  然后，A2A客户端带外获取这些新凭证，并在后续的`message/send`或`message/stream`请求中提供它们。这些凭证如何使用（例如，如果代理是代理，则作为A2A消息中的数据传递，或者由客户端直接与次要系统交互）取决于具体场景。

### 4.6. 授权

一旦客户端被认证，A2A服务器负责根据认证的客户端/用户身份及其自己的策略来授权请求。授权逻辑是实现特定的，**可以**基于以下内容强制执行：

  * 请求的特定技能（例如，由代理卡中的`AgentSkill.id`标识）。
  * 任务中尝试的操作。
  * 与代理管理的资源相关的数据访问策略。
  * 如果适用，与所提交令牌关联的OAuth范围。

服务器应实施最小权限原则。

## 5\. 代理发现：代理卡

### 5.1. 目的

A2A服务器**必须**提供一个代理卡。代理卡是一个JSON文档，描述了服务器的身份、能力、技能、服务端点URL以及客户端应如何认证和与之交互。客户端使用此信息来发现合适的代理并配置其交互。

更多关于发现策略的信息，请参阅[代理发现指南](https://a2a-protocol.org/latest/topics/agent-discovery/)。

### 5.2. 发现机制

客户端可以通过各种方法找到代理卡，包括但不限于：

  * **众所周知的URI：** 访问代理域上的预定义路径（参见第5.3节）。
  * **注册中心/目录：** 查询代理的策展目录或注册中心（可能是企业特定、公共或领域特定的）。
  * **直接配置：** 客户端可以预先配置代理卡的URL或卡片内容本身。

### 5.3. 推荐位置

如果使用众所周知的URI策略，代理卡的推荐位置是：
`https://{server_domain}/.well-known/agent-card.json`
这遵循了[RFC 8615](https://datatracker.ietf.org/doc/html/rfc8615)关于众所周知URI的原则。

### 5.4. 代理卡的安全性

代理卡本身可能包含被视为敏感的信息。

  * 如果代理卡包含敏感信息，提供该卡的端点**必须**受到适当的访问控制保护（例如，mTLS、网络限制、获取卡片需要认证）。
  * 通常**不推荐**在代理卡中直接包含明文秘密（如静态API密钥）。倾向于使用客户端带外获取动态凭证的认证方案。

### 5.5. `AgentCard` 对象结构

```ts
/**
 * AgentCard是代理的自描述清单。它提供基本的元数据，包括代理的身份、能力、技能、支持的通信方法和安全要求。
 */
export interface AgentCard {
  /**
   * 此代理支持的A2A协议版本。
   * @default "0.3.0"
   */
  protocolVersion: string;
  /**
   * 代理的人类可读名称。
   * @TJS-examples ["Recipe Agent"]
   */
  name: string;
  /**
   * 代理的人类可读描述，帮助用户和其他代理理解其目的。
   * @TJS-examples ["帮助用户处理食谱和烹饪的代理。"]
   */
  description: string;
  /**
   * 与代理交互的首选端点URL。此URL必须支持由'preferredTransport'指定的传输。
   * @TJS-examples ["https://api.example.com/a2a/v1"]
   */
  url: string;
  /**
   * 首选端点（主'url'字段）的传输协议。如果未指定，默认为'JSONRPC'。
   * 重要：此处指定的传输必须在主'url'上可用。这在主URL和其支持的传输协议之间创建了绑定。当两者都支持时，客户端应首选此传输和URL组合。
   * @default "JSONRPC"
   * @TJS-examples ["JSONRPC", "GRPC", "HTTP+JSON"]
   */
  preferredTransport?: TransportProtocol | string;
  /**
   * 支持的附加接口列表（传输和URL组合）。这允许代理暴露多种传输，可能在不同的URL上。
   * 最佳实践：
   * - 应包括所有支持的传输以求完整
   * - 应包括一个与主'url'和'preferredTransport'匹配的条目
   * - 如果多个传输在同一端点可用，可以重用URL
   * - 必须准确声明每个URL上可用的传输
   * 客户端可以根据其传输能力和偏好从此列表中选择任何接口。这使得传输协商和回退场景成为可能。
   */
  additionalInterfaces?: AgentInterface[];
  /** 代理图标的可选URL。 */
  iconUrl?: string;
  /** 关于代理服务提供商的信息。 */
  provider?: AgentProvider;
  /**
   * 代理自身的版本号。格式由提供商定义。
   * @TJS-examples ["1.0.0"]
   */
  version: string;
  /** 代理文档的可选URL。 */
  documentationUrl?: string;
  /** 代理支持的可选能力的声明。 */
  capabilities: AgentCapabilities;
  /**
   * 用于授权请求的安全方案声明。键是方案名称。遵循OpenAPI 3.0安全方案对象。
   */
  securitySchemes?: { [scheme: string]: SecurityScheme };
  /**
   * 适用于所有代理交互的安全要求对象列表。每个对象列出了可以使用的安全方案。遵循OpenAPI 3.0安全要求对象。此列表可视为AND的OR。列表中的每个对象描述了一组可能必须存在于请求上的安全要求。例如，这允许指定“调用者必须使用OAuth或API密钥和mTLS”。
   * @TJS-examples [[{"oauth": ["read"]}, {"api-key": [], "mtls": []}]]
   */
  security?: { [scheme: string]: string[] }[];
  /**
   * 所有技能支持的默认输入MIME类型集，可以在每个技能的基础上被覆盖。
   */
  defaultInputModes: string[];
  /**
   * 所有技能支持的默认输出MIME类型集，可以在每个技能的基础上被覆盖。
   */
  defaultOutputModes: string[];
  /** 代理可以执行的技能或不同能力的集合。 */
  skills: AgentSkill[];
  /**
   * 如果为true，代理可以向认证用户提供带有附加细节的扩展代理卡。默认为false。
   */
  supportsAuthenticatedExtendedCard?: boolean;
  /** 为此AgentCard计算的JSON Web签名。 */
  signatures?: AgentCardSignature[];
}
```

#### 5.5.1. `AgentProvider` 对象

关于提供代理的组织或实体的信息。

```ts
/**
 * 代表代理的服务提供商。
 * @TJS-examples [{ "organization": "Google", "url": "https://ai.google.dev" }]
 */
export interface AgentProvider {
  /** 代理提供商组织的名称。 */
  organization: string;
  /** 代理提供商网站或相关文档的URL。 */
  url: string;
}
```

#### 5.5.2. `AgentCapabilities` 对象

指定代理支持的可选A2A协议功能。

```ts
/**
 * 定义代理支持的可选能力。
 */
export interface AgentCapabilities {
  /** 指示代理是否支持服务器发送事件(SSE)以进行流式响应。 */
  streaming?: boolean;
  /** 指示代理是否支持发送推送通知以进行异步任务更新。 */
  pushNotifications?: boolean;
  /** 指示代理是否为任务提供状态转换历史记录。 */
  stateTransitionHistory?: boolean;
  /** 代理支持的协议扩展列表。 */
  extensions?: AgentExtension[];
}
```

#### 5.5.2.1. `AgentExtension` 对象

指定代理支持的A2A协议扩展。

```ts
/**
 * 代理支持的协议扩展的声明。
 * @TJS-examples [{"uri": "https://developers.google.com/identity/protocols/oauth2", "description": "Google OAuth 2.0 authentication", "required": false}]
 */
export interface AgentExtension {
  /** 唯一标识扩展的URI。 */
  uri: string;
  /** 此代理如何使用扩展的人类可读描述。 */
  description?: string;
  /**
   * 如果为true，客户端必须理解并遵守扩展的要求才能与代理交互。
   */
  required?: boolean;
  /** 可选的、特定于扩展的配置参数。 */
  params?: { [key: string]: any };
}
```

#### 5.5.3. `SecurityScheme` 对象

描述访问代理`url`端点的认证要求。请参考[示例代理卡](https://www.google.com/search?q=%2357-sample-agent-card)获取示例。

```ts
/**
 * 定义可用于保护代理端点的安全方案。这是一个基于OpenAPI 3.0安全方案对象的区分联合类型。
 * @see {@link https://swagger.io/specification/#security-scheme-object}
 */
export type SecurityScheme =
  | APIKeySecurityScheme
  | HTTPAuthSecurityScheme
  | OAuth2SecurityScheme
  | OpenIdConnectSecurityScheme
  | MutualTLSSecurityScheme;
```

#### 5.5.4. `AgentSkill` 对象

描述代理可以执行或处理的特定能力、功能或专业领域。

```ts
/**
 * 代表代理可以执行的独特能力或功能。
 */
export interface AgentSkill {
  /** 代理技能的唯一标识符。 */
  id: string;
  /** 技能的人类可读名称。 */
  name: string;
  /**
   * 技能的详细描述，旨在帮助客户端或用户理解其目的和功能。
   */
  description: string;
  /**
   * 描述技能能力的关键字集。
   * @TJS-examples [["cooking", "customer support", "billing"]]
   */
  tags: string[];
  /**
   * 此技能可以处理的示例提示或场景。为客户端如何使用技能提供提示。
   * @TJS-examples [["I need a recipe for bread"]]
   */
  examples?: string[];
  /**
   * 此技能支持的输入MIME类型集，覆盖代理的默认值。
   */
  inputModes?: string[];
  /**
   * 此技能支持的输出MIME类型集，覆盖代理的默认值。
   */
  outputModes?: string[];
  /**
   * 代理利用此技能所需的安全方案。与整个AgentCard.security一样，此列表代表安全要求对象的逻辑OR。每个对象是必须一起使用的安全方案集（逻辑AND）。
   * @TJS-examples [[{"google": ["oidc"]}]]
   */
  security?: { [scheme: string]: string[] }[];
}
```

#### 5.5.5. `AgentInterface` 对象

提供目标URL和与代理交互的支持传输的组合声明。这使代理能够通过多种传输协议暴露相同的功能。

```ts
/**
 * 支持的A2A传输协议。
 */
export enum TransportProtocol {
  JSONRPC = "JSONRPC", // JSON-RPC 2.0 over HTTP (强制)
  GRPC = "GRPC", // gRPC over HTTP/2 (可选)
  HTTP_JSON = "HTTP+JSON", // REST-style HTTP with JSON (可选)
}
```

```ts
/**
 * 声明目标URL和与代理交互的传输协议的组合。这允许代理通过多种传输机制暴露相同的功能。
 */
export interface AgentInterface {
  /**
   * 此接口可用的URL。在生产环境中必须是有效的绝对HTTPS URL。
   * @TJS-examples ["https://api.example.com/a2a/v1", "https://grpc.example.com/a2a", "https://rest.example.com/v1"]
   */
  url: string;
  /**
   * 此URL支持的传输协议。
   * @TJS-examples ["JSONRPC", "GRPC", "HTTP+JSON"]
   */
  transport: TransportProtocol | string;
}
```

`transport` 字段 **应该** 使用核心A2A传输协议值之一：

  * `"JSONRPC"`: JSON-RPC 2.0 over HTTP
  * `"GRPC"`: gRPC over HTTP/2
  * `"HTTP+JSON"`: REST-style HTTP with JSON

额外的传输值 **可以** 用于未来的扩展，但此类扩展 **必须** 不与核心A2A协议功能冲突。

#### 5.5.6. `AgentCardSignature` 对象

表示用于验证代理卡完整性的JSON Web签名（JWS）。

```ts
/**
 * AgentCardSignature表示AgentCard的JWS签名。这遵循RFC 7515 JSON Web签名（JWS）的JSON格式。
 */
export interface AgentCardSignature {
  /**
   * 签名的受保护JWS头。这是一个Base64url编码的JSON对象，根据RFC 7515。
   */
  protected: string;
  /** 计算出的签名，Base64url编码。 */
  signature: string;
  /** 不受保护的JWS头值。 */
  header?: { [key: string]: any };
}
```

### 5.6. 传输声明和URL关系

代理卡**必须**正确声明URL和传输协议之间的关系：

#### 5.6.1. 主URL和首选传输

  * **主URL要求**：`url`字段**必须**指定代理的主要端点。
  * **传输对应**：主`url`上可用的传输协议**必须**与`preferredTransport`字段匹配。
  * **必需声明**：`preferredTransport`字段是**必需的**，并且**必须**存在于每个`AgentCard`中。
  * **传输可用性**：主`url`**必须**支持`preferredTransport`中声明的传输协议。

#### 5.6.2. 附加接口

  * **URL唯一性**：为清晰起见，`additionalInterfaces`中的每个`AgentInterface`**应该**指定一个唯一的URL，但如果多个传输协议在同一端点可用，则**可以**重用URL。
  * **传输声明**：每个`AgentInterface`**必须**准确声明其指定URL上可用的传输协议。
  * **完整性**：为完整起见，`additionalInterfaces`数组**应该**包括与主URL的传输相对应的条目。

#### 5.6.3. 客户端传输选择规则

客户端在选择传输时**必须**遵循以下规则：

1.  **解析传输声明**：从主`url`/`preferredTransport`组合和所有`additionalInterfaces`中提取可用的传输。
2.  **偏好声明的偏好**：如果客户端支持`preferredTransport`，它**应该**使用主`url`。
3.  **回退选择**：如果客户端不支持首选传输，它**可以**从`additionalInterfaces`中选择任何支持的传输。
4.  **优雅降级**：如果首选失败，客户端**应该**实现回退逻辑以尝试其他传输。
5.  **URL-传输匹配**：客户端**必须**为所选的传输协议使用代理卡中声明的正确URL。

#### 5.6.4. 验证要求

代理卡**必须**满足以下验证要求：

  * **传输一致性**：`preferredTransport`值**必须**存在，并且**必须**在主`url`上可用。
  * **接口完整性**：如果提供了`additionalInterfaces`，它**应该**包括一个与主`url`和`preferredTransport`相对应的条目。
  * **无冲突**：同一URL**不得**在不同的接口声明中声明冲突的传输协议。
  * **最低传输要求**：代理**必须**通过主`url`/`preferredTransport`组合或`additionalInterfaces`声明至少一个支持的传输协议。

### 5.7. 示例代理卡

```json
{
  "protocolVersion": "0.2.9",
  "name": "GeoSpatial Route Planner Agent",
  "description": "Provides advanced route planning, traffic analysis, and custom map generation services. This agent can calculate optimal routes, estimate travel times considering real-time traffic, and create personalized maps with points of interest.",
  "url": "https://georoute-agent.example.com/a2a/v1",
  "preferredTransport": "JSONRPC",
  "additionalInterfaces" : [
    {"url": "https://georoute-agent.example.com/a2a/v1", "transport": "JSONRPC"},
    {"url": "https://georoute-agent.example.com/a2a/grpc", "transport": "GRPC"},
    {"url": "https://georoute-agent.example.com/a2a/json", "transport": "HTTP+JSON"}
  ],
  "provider": {
    "organization": "Example Geo Services Inc.",
    "url": "https://www.examplegeoservices.com"
  },
  "iconUrl": "https://georoute-agent.example.com/icon.png",
  "version": "1.2.0",
  "documentationUrl": "https://docs.examplegeoservices.com/georoute-agent/api",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "stateTransitionHistory": false
  },
  "securitySchemes": {
    "google": {
      "type": "openIdConnect",
      "openIdConnectUrl": "https://accounts.google.com/.well-known/openid-configuration"
    }
  },
  "security": [{"google": ["openid", "profile", "email"]}],
  "defaultInputModes": ["application/json", "text/plain"],
  "defaultOutputModes": ["application/json", "image/png"],
  "skills": [
    {
      "id": "route-optimizer-traffic",
      "name": "Traffic-Aware Route Optimizer",
      "description": "Calculates the optimal driving route between two or more locations, taking into account real-time traffic conditions, road closures, and user preferences (e.g., avoid tolls, prefer highways).",
      "tags": ["maps", "routing", "navigation", "directions", "traffic"],
      "examples": [
        "Plan a route from '1600 Amphitheatre Parkway, Mountain View, CA' to 'San Francisco International Airport' avoiding tolls.",
        "{\"origin\": {\"lat\": 37.422, \"lng\": -122.084}, \"destination\": {\"lat\": 37.7749, \"lng\": -122.4194}, \"preferences\": [\"avoid_ferries\"]}"
      ],
      "inputModes": ["application/json", "text/plain"],
      "outputModes": [
        "application/json",
        "application/vnd.geo+json",
        "text/html"
      ]
    },
    {
      "id": "custom-map-generator",
      "name": "Personalized Map Generator",
      "description": "Creates custom map images or interactive map views based on user-defined points of interest, routes, and style preferences. Can overlay data layers.",
      "tags": ["maps", "customization", "visualization", "cartography"],
      "examples": [
        "Generate a map of my upcoming road trip with all planned stops highlighted.",
        "Show me a map visualizing all coffee shops within a 1-mile radius of my current location."
      ],
      "inputModes": ["application/json"],
      "outputModes": [
        "image/png",
        "image/jpeg",
        "application/json",
        "text/html"
      ]
    }
  ],
  "supportsAuthenticatedExtendedCard": true,
  "signatures": [
    {
      "protected": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpPU0UiLCJraWQiOiJrZXktMSIsImprdSI6Imh0dHBzOi8vZXhhbXBsZS5jb20vYWdlbnQvandrcy5qc29uIn0",
      "signature": "QFdkNLNszlGj3z3u0YQGt_T9LixY3qtdQpZmsTdDHDe3fXV9y9-B3m2-XgCpzuhiLt8E0tV6HXoZKHv4GtHgKQ"
    }
  ]
}
```

## 6\. 协议数据对象

这些对象定义了在A2A协议的JSON-RPC方法中交换的数据结构。

### 6.1. `Task` 对象

表示A2A服务器为A2A客户端处理的有状态工作单元。任务封装了与特定目标或请求相关的整个交互。已达到终端状态（完成、取消、拒绝或失败）的任务无法重新启动。处于完成状态的任务应使用工件将生成的输出返回给客户端。有关更多信息，请参阅[任务的生命周期指南](https://a2a-protocol.org/latest/topics/life-of-a-task/)。

```ts
/**
 * 代表客户端和代理之间的单个有状态操作或对话。
 */
export interface Task {
  /** 任务的唯一标识符，由服务器为新任务生成。 */
  id: string;
  /** 服务器生成的标识符，用于在多个相关任务或交互中维护上下文。 */
  contextId: string;
  /** 任务的当前状态，包括其状态和描述性消息。 */
  status: TaskStatus;
  /** 任务期间交换的消息数组，代表对话历史。 */
  history?: Message[];
  /** 代理在执行任务期间生成的工件集合。 */
  artifacts?: Artifact[];
  /** 扩展的可选元数据。键是扩展特定的标识符。 */
  metadata?: {
    [key: string]: any;
  };
  /** 此对象的类型，用作鉴别器。对于Task始终为'task'。 */
  readonly kind: "task";
}
```

### 6.2. `TaskStatus` 对象

表示`Task`的当前状态及相关上下文（例如，来自代理的消息）。

```ts
/**
 * 表示任务在特定时间点的状态。
 */
export interface TaskStatus {
  /** 任务生命周期的当前状态。 */
  state: TaskState;
  /** 可选的、人类可读的消息，提供有关当前状态的更多详细信息。 */
  message?: Message;
  /**
   * ISO 8601日期时间字符串，指示此状态的记录时间。
   * @TJS-examples ["2023-10-27T10:00:00Z"]
   */
  timestamp?: string;
}
```

### 6.3. `TaskState` 枚举

定义`Task`可能的生命周期状态。

```ts
/**
 * 定义任务的生命周期状态。
 */
export enum TaskState {
  /** 任务已提交，等待执行。 */
  Submitted = "submitted",
  /** 代理正在积极处理任务。 */
  Working = "working",
  /** 任务已暂停，等待用户输入。 */
  InputRequired = "input-required",
  /** 任务已成功完成。 */
  Completed = "completed",
  /** 任务已被用户取消。 */
  Canceled = "canceled",
  /** 任务因执行期间出错而失败。 */
  Failed = "failed",
  /** 任务被代理拒绝，未启动。 */
  Rejected = "rejected",
  /** 任务需要认证才能继续。 */
  AuthRequired = "auth-required",
  /** 任务处于未知或不确定状态。 */
  Unknown = "unknown",
}
```

### 6.4. `Message` 对象

表示客户端和代理之间的单个通信回合或一条上下文信息。消息用于指令、提示、回复和状态更新。

```ts
/**
 * 表示用户和代理之间对话中的单个消息。
 */
export interface Message {
  /** 标识消息的发送者。'user'表示客户端，'agent'表示服务。 */
  readonly role: "user" | "agent";
  /**
   * 构成消息正文的内容部件数组。一条消息可以由不同类型的多个部件组成（例如，文本和文件）。
   */
  parts: Part[];
  /** 扩展的可选元数据。键是扩展特定的标识符。 */
  metadata?: {
    [key: string]: any;
  };
  /** 与此消息相关的扩展的URI。 */
  extensions?: string[];
  /** 此消息引用的其他任务ID，用于提供附加上下文。 */
  referenceTaskIds?: string[];
  /** 消息的唯一标识符，通常是UUID，由发送方生成。 */
  messageId: string;
  /** 此消息所属任务的标识符。对于新任务的第一条消息可以省略。 */
  taskId?: string;
  /** 此消息的上下文标识符，用于分组相关交互。 */
  contextId?: string;
  /** 此对象的类型，用作鉴别器。对于Message始终为'message'。 */
  readonly kind: "message";
}
```

### 6.5. `Part` 联合类型

表示`Message`或`Artifact`中的一个独特内容块。`Part`是一个联合类型，表示可导出内容为`TextPart`、`FilePart`或`DataPart`。所有`Part`类型还包括一个可选的`metadata`字段（`Record<string, any>`），用于部件特定的元数据。

```ts
/**
 * 表示消息或工件的一部分的区分联合类型，可以是文本、文件或结构化数据。
 */
export type Part = TextPart | FilePart | DataPart;
```

```ts
/**
 * 定义所有消息或工件部件共有的基本属性。
 */
export interface PartBase {
  /** 与此部件关联的可选元数据。 */
  metadata?: {
    [key: string]: any;
  };
}
```

它**必须**是以下之一：

#### 6.5.1. `TextPart` 对象

用于传达纯文本内容。

```ts
/**
 * 表示消息或工件中的文本段。
 */
export interface TextPart extends PartBase {
  /** 此部件的类型，用作鉴别器。始终为'text'。 */
  readonly kind: "text";
  /** 文本部件的字符串内容。 */
  text: string;
}
```

#### 6.5.2. `FilePart` 对象

用于传达基于文件的内容。

```ts
/**
 * 表示消息或工件中的文件段。文件内容可以直接作为字节或作为URI提供。
 */
export interface FilePart extends PartBase {
  /** 此部件的类型，用作鉴别器。始终为'file'。 */
  readonly kind: "file";
  /** 文件内容，表示为URI或base64编码的字节。 */
  file: FileWithBytes | FileWithUri;
}
```

#### 6.5.3. `DataPart` 对象

用于传达结构化的JSON数据。适用于表单、参数或任何机器可读的信息。

```ts
/**
 * 表示消息或工件中的结构化数据段（例如，JSON）。
 */
export interface DataPart extends PartBase {
  /** 此部件的类型，用作鉴别器。始终为'data'。 */
  readonly kind: "data";
  /** 结构化数据内容。 */
  data: {
    [key: string]: any;
  };
}
```

### 6.6 `FileBase` 对象

文件内容的基础实体。

```ts
/**
 * 定义文件的基本属性。
 */
export interface FileBase {
  /** 文件的可选名称（例如，"document.pdf"）。 */
  name?: string;
  /** 文件的MIME类型（例如，"application/pdf"）。 */
  mimeType?: string;
}
```

#### 6.6.1 `FileWithBytes` 对象

表示文件的数据，在`FilePart`中使用。

```ts
/**
 * 表示一个文件，其内容直接以base64编码的字符串形式提供。
 */
export interface FileWithBytes extends FileBase {
  /** 文件的base64编码内容。 */
  bytes: string;
  /** 当`bytes`存在时，`uri`属性必须不存在。 */
  uri?: never;
}
```

#### 6.6.2 `FileWithUri` 对象

表示文件的URI，在`FilePart`中使用。

```ts
/**
 * 表示一个文件，其内容位于特定的URI。
 */
export interface FileWithUri extends FileBase {
  /** 指向文件内容的URL。 */
  uri: string;
  /** 当`uri`存在时，`bytes`属性必须不存在。 */
  bytes?: never;
}
```

### 6.7. `Artifact` 对象

表示代理在任务期间生成的有形输出。工件是代理工作的结果或产品。

```ts
/**
 * 表示代理在任务期间生成的文件、数据结构或其他资源。
 */
export interface Artifact {
  /** 任务范围内工件的唯一标识符。 */
  artifactId: string;
  /** 工件的可选、人类可读名称。 */
  name?: string;
  /** 工件的可选、人类可读描述。 */
  description?: string;
  /** 构成工件的内容部件数组。 */
  parts: Part[];
  /** 扩展的可选元数据。键是扩展特定的标识符。 */
  metadata?: {
    [key: string]: any;
  };
  /** 与此工件相关的扩展的URI。 */
  extensions?: string[];
}
```

### 6.8. `PushNotificationConfig` 对象

客户端提供给服务器的配置，用于发送关于任务更新的异步推送通知。

```ts
/**
 * 定义设置任务更新推送通知的配置。
 */
export interface PushNotificationConfig {
  /**
   * 推送通知配置的唯一ID，由客户端设置，以支持多个通知回调。
   */
  id?: string;
  /** 代理应向其发送推送通知的回调URL。 */
  url: string;
  /** 用于验证传入推送通知的此任务或会话的唯一令牌。 */
  token?: string;
  /** 代理在调用通知URL时使用的可选认证详细信息。 */
  authentication?: PushNotificationAuthenticationInfo;
}
```

### 6.9. `PushNotificationAuthenticationInfo` 对象

用于指定认证要求的通用结构，通常在`PushNotificationConfig`中使用，以描述A2A服务器应如何向客户端的webhook进行认证。

```ts
/**
 * 定义推送通知端点的认证详细信息。
 */
export interface PushNotificationAuthenticationInfo {
  /** 支持的认证方案列表（例如，'Basic'，'Bearer'）。 */
  schemes: string[];
  /** 推送通知端点所需的可选凭证。 */
  credentials?: string;
}
```

### 6.10. `TaskPushNotificationConfig` 对象

用作`tasks/pushNotificationConfig/set`方法的`params`对象和`tasks/pushNotificationConfig/get`方法的`result`对象。

```ts
/**
 * 将推送通知配置与特定任务关联的容器。
 */
export interface TaskPushNotificationConfig {
  /** 任务的ID。 */
  taskId: string;
  /** 此任务的推送通知配置。 */
  pushNotificationConfig: PushNotificationConfig;
}
```

### 6.11. JSON-RPC 结构

A2A遵循标准的[JSON-RPC 2.0](https://www.jsonrpc.org/specification)请求和响应结构。

#### 6.11.1. `JSONRPCRequest` 对象

所有A2A方法调用都封装在JSON-RPC请求对象中。

  * `jsonrpc`：指定JSON-RPC协议版本的字符串。**必须**是`"2.0"`。
  * `method`：包含要调用方法名称的字符串（例如，`"message/send"`，`"tasks/get"`）。
  * `params`：一个结构化值，包含方法调用期间要使用的参数值。如果方法不需要参数，则此成员**可以**省略。A2A方法通常为`params`使用`object`。
  * `id`：由客户端建立的标识符，如果包含，**必须**包含字符串、数字或`NULL`值。如果不包含，则假定为通知。对于期望响应的请求，该值**不应该**为`NULL`，并且数字**不应该**包含小数部分。如果包含，服务器**必须**在响应对象中回复相同的值。此成员用于关联两个对象之间的上下文。A2A方法通常期望响应或流，因此`id`通常会存在且不为null。

#### 6.11.2. `JSONRPCResponse` 对象

来自A2A服务器的响应封装在JSON-RPC响应对象中。

  * `jsonrpc`：指定JSON-RPC协议版本的字符串。**必须**是`"2.0"`。
  * `id`：此成员是**必需的**。它**必须**与请求对象中`id`成员的值相同。如果在请求对象中检测`id`时出错（例如，解析错误/无效请求），则**必须**为`null`。
  * **要么** `result`：此成员在成功时是**必需的**。如果在调用方法时出错，则此成员**不得**存在。此成员的值由服务器上调用的方法决定。
  * **要么** `error`：此成员在失败时是**必需的**。如果在调用期间没有触发错误，则此成员**不得**存在。此成员的值**必须**是`JSONRPCError`对象。
  * `result`和`error`成员是互斥的：**必须**有一个存在，另一个**不得**存在。

### 6.12. `JSONRPCError` 对象

当JSON-RPC调用遇到错误时，响应对象将包含一个`error`成员，其值为此结构。

```ts
/**
 * 表示JSON-RPC 2.0错误对象，包含在错误响应中。
 */
export interface JSONRPCError {
  /**
   * 表示发生的错误类型的数字。
   */
  code: number;
  /**
   * 提供错误简短描述的字符串。
   */
  message: string;
  /**
   * 包含有关错误的附加信息的原始或结构化值。可以省略。
   */
  data?: any;
}
```

## 7\. 协议 RPC 方法

所有 A2A RPC 方法都由 A2A 客户端通过向 A2A 服务器的 `url`（在其 `AgentCard` 中指定）发送 HTTP POST 请求来调用。HTTP POST 请求的正文**必须**是 `JSONRPCRequest` 对象，`Content-Type` 头部**必须**是 `application/json`。

A2A 服务器的 HTTP 响应正文**必须**是 `JSONRPCResponse` 对象（或者，对于流式方法，是一个 SSE 流，其中每个事件的数据都是一个 `JSONRPCResponse`）。JSON-RPC 响应的 `Content-Type` 是 `application/json`。对于 SSE 流，它是 `text/event-stream`。

### 7.1. `message/send`

向代理发送消息以启动新的交互或继续现有的交互。此方法适用于同步请求/响应交互，或者当客户端轮询（使用 `tasks/get`）对于监控长时间运行的任务是可接受的时候。已达到终端状态（完成、取消、拒绝或失败）的任务无法重新启动。向此类任务发送消息将导致错误。有关更多信息，请参阅[任务的生命周期指南](https://a2a-protocol.org/latest/topics/life-of-a-task/)。

  * **URL:** `message/send`
  * **HTTP 方法:** `POST`
  * **负载:** `MessageSendParams`
  * **响应:** `Task` | `Message` (一个消息对象或处理消息后任务的当前或最终状态)。

#### 7.1.1. `MessageSendParams` 对象

```typescript
/**
 * 定义向代理发送消息的请求参数。这可以用于创建新任务、继续现有任务或重新启动任务。
 */
export interface MessageSendParams {
  /** 正在发送给代理的消息对象。 */
  message: Message;
  /** 发送请求的可选配置。 */
  configuration?: MessageSendConfiguration;
  /** 扩展的可选元数据。 */
  metadata?: {
    [key: string]: any;
  };
}

/**
 * 定义`message/send`或`message/stream`请求的配置选项。
 */
export interface MessageSendConfiguration {
  /** 客户端准备在响应中接受的输出MIME类型列表。 */
  acceptedOutputModes?: string[];
  /** 从任务历史中检索的最新消息数。 */
  historyLength?: number;
  /** 代理在初始响应后发送更新的推送通知配置。 */
  pushNotificationConfig?: PushNotificationConfig;
  /** 如果为true，客户端将等待任务完成。如果任务是长时间运行的，服务器可能会拒绝此请求。 */
  blocking?: boolean;
}
```

### 7.2. `message/stream`

向代理发送消息以启动/继续任务，并订阅客户端以通过服务器发送事件(SSE)接收该任务的实时更新。此方法要求服务器的`AgentCard.capabilities.streaming: true`。与`message/send`一样，已达到终端状态（完成、取消、拒绝或失败）的任务无法重新启动。向此类任务发送消息将导致错误。有关更多信息，请参阅[任务的生命周期指南](https://a2a-protocol.org/latest/topics/life-of-a-task/)。

  * **URL:** `message/stream`
  * **HTTP 方法:** `POST`
  * **负载:** `MessageSendParams` (与 `message/send` 相同)
  * **响应:** 服务器发送事件流。每个 SSE `data` 字段包含一个 `SendStreamingMessageResponse`。

#### 7.2.1. `SendStreamingMessageResponse` 对象

这是在`message/stream`或`tasks/resubscribe`请求中，服务器发送的每个服务器发送事件的`data`字段中找到的JSON对象的结构。

```typescript
/**
 * 表示`message/stream`方法的JSON-RPC响应。
 */
export type SendStreamingMessageResponse =
  | SendStreamingMessageSuccessResponse
  | JSONRPCErrorResponse;

/**
 * 表示`message/stream`方法的成功JSON-RPC响应。服务器可以为单个请求发送多个响应对象。
 */
export interface SendStreamingMessageSuccessResponse
  extends JSONRPCSuccessResponse {
  /** 结果，可以是Message、Task或流式更新事件。 */
  result: Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent;
}
```

#### 7.2.2. `TaskStatusUpdateEvent` 对象

在流式传输期间携带有关任务状态变化的信息。这是`SendStreamingMessageSuccessResponse`中可能的结果类型之一。

```typescript
/**
 * 代理发送的事件，用于通知客户端任务状态的更改。这通常用于流式传输或订阅模型。
 */
export interface TaskStatusUpdateEvent {
  /** 已更新任务的ID。 */
  taskId: string;
  /** 与任务关联的上下文ID。 */
  contextId: string;
  /** 此事件的类型，用作鉴别器。始终为'status-update'。 */
  readonly kind: "status-update";
  /** 任务的新状态。 */
  status: TaskStatus;
  /** 如果为true，则这是此交互流中的最后一个事件。 */
  final: boolean;
  /** 扩展的可选元数据。 */
  metadata?: {
    [key: string]: any;
  };
}
```

#### 7.2.3. `TaskArtifactUpdateEvent` 对象

在流式传输期间，携带由任务生成的新或更新的工件（或工件块）。这是`SendTaskStreamingResponse`中可能的结果类型之一。

```typescript
/**
 * 代理发送的事件，用于通知客户端工件已生成或更新。这通常用于流式模型。
 */
export interface TaskArtifactUpdateEvent {
  /** 此工件所属任务的ID。 */
  taskId: string;
  /** 与任务关联的上下文ID。 */
  contextId: string;
  /** 此事件的类型，用作鉴别器。始终为'artifact-update'。 */
  readonly kind: "artifact-update";
  /** 已生成或更新的工件。 */
  artifact: Artifact;
  /** 如果为true，此工件的内容应附加到先前发送的具有相同ID的工件。 */
  append?: boolean;
  /** 如果为true，则这是工件的最后一个块。 */
  lastChunk?: boolean;
  /** 扩展的可选元数据。 */
  metadata?: {
    [key: string]: any;
  };
}
```

### 7.3. `tasks/get`

检索先前启动任务的当前状态（包括状态、工件和可选的历史记录）。这通常用于轮询由`message/send`启动的任务的状态，或在通过推送通知或SSE流结束后获取任务的最终状态。

  * **URL:** `tasks/get`
  * **HTTP 方法:** `POST`
  * **负载:** `TaskQueryParams`
  * **响应:** `Task`

#### 7.3.1. `TaskQueryParams` 对象

```typescript
/**
 * 定义查询任务的参数，并可选择限制历史记录长度。
 */
export interface TaskQueryParams extends TaskIdParams {
  /** 要检索的任务历史中最新消息的数量。 */
  historyLength?: number;
}
```

### `tasks/list`

  * **JSON-RPC:** N/A
  * **gRPC:** `ListTask` (GET) - 响应 `repeated Task`
  * **REST:** `GET /v1/tasks` - 响应 `[Task]`

### 7.4. `tasks/cancel`

请求取消正在进行的任务。服务器将尝试取消任务，但不能保证成功（例如，任务可能已经完成或失败，或者在其当前阶段不支持取消）。

  * **URL:** `tasks/cancel`
  * **HTTP 方法:** `POST`
  * **负载:** `TaskIdParams`
  * **响应:** `Task`

#### 7.4.1. `TaskIdParams` 对象 (用于 `tasks/cancel` 和 `tasks/pushNotificationConfig/get`)

一个只包含任务ID和可选元数据的简单对象。

```typescript
/**
 * 定义包含任务ID的参数，用于简单的任务操作。
 */
export interface TaskIdParams {
  /** 任务的唯一标识符。 */
  id: string;
  /** 与请求关联的可选元数据。 */
  metadata?: {
    [key: string]: any;
  };
}
```

### 7.5. `tasks/pushNotificationConfig/set`

为指定的任务设置或更新推送通知配置。这允许客户端告诉服务器在哪里以及如何为任务发送异步更新。要求服务器的`AgentCard.capabilities.pushNotifications: true`。

  * **URL:** `tasks/pushNotificationConfig/set`
  * **HTTP 方法:** `POST`
  * **负载:** `TaskPushNotificationConfig`
  * **响应:** `TaskPushNotificationConfig`

### 7.6. `tasks/pushNotificationConfig/get`

检索指定任务的当前推送通知配置。要求服务器的`AgentCard.capabilities.pushNotifications: true`。

  * **URL:** `tasks/pushNotificationConfig/get`
  * **HTTP 方法:** `POST`
  * **负载:** `GetTaskPushNotificationConfigParams`
  * **响应:** `TaskPushNotificationConfig`

#### 7.6.1. `GetTaskPushNotificationConfigParams` 对象 (`tasks/pushNotificationConfig/get`)

用于获取任务推送通知配置的对象。

```typescript
/**
 * 定义用于获取任务特定推送通知配置的参数。
 */
export interface GetTaskPushNotificationConfigParams extends TaskIdParams {
  /** 要检索的推送通知配置的ID。 */
  pushNotificationConfigId?: string;
}
```

### 7.7. `tasks/pushNotificationConfig/list`

检索指定任务关联的推送通知配置。要求服务器的`AgentCard.capabilities.pushNotifications: true`。

  * **URL:** `tasks/pushNotificationConfig/list`
  * **HTTP 方法:** `POST`
  * **负载:** `ListTaskPushNotificationConfigParams`
  * **响应:** `TaskPushNotificationConfig[]`

#### 7.7.1. `ListTaskPushNotificationConfigParams` 对象 (`tasks/pushNotificationConfig/list`)

用于获取任务所有推送通知配置的对象。

```typescript
/**
 * 定义用于列出与任务关联的所有推送通知配置的参数。
 */
export interface ListTaskPushNotificationConfigParams extends TaskIdParams {}
```

### 7.8. `tasks/pushNotificationConfig/delete`

删除任务的关联推送通知配置。要求服务器的`AgentCard.capabilities.pushNotifications: true`。

  * **请求 `params` 类型:** `DeleteTaskPushNotificationConfigParams`
  * **响应 `result` 类型 (成功时):** `null`
  * **响应 `error` 类型 (失败时):** `JSONRPCError`

#### 7.8.1. `DeleteTaskPushNotificationConfigParams` 对象 (`tasks/pushNotificationConfig/delete`)

用于删除任务关联推送通知配置的对象。

```typescript
/**
 * 定义用于删除任务特定推送通知配置的参数。
 */
export interface DeleteTaskPushNotificationConfigParams extends TaskIdParams {
  /** 要删除的推送通知配置的ID。 */
  pushNotificationConfigId: string;
}
```

### 7.9. `tasks/resubscribe`

允许客户端在先前的连接（来自`message/stream`或更早的`tasks/resubscribe`）中断后，重新连接到正在进行的任务的SSE流。要求服务器的`AgentCard.capabilities.streaming: true`。

  * **URL:** `tasks/resubscribe`
  * **HTTP 方法:** `POST`
  * **负载:** `TaskIdParams`
  * **响应:** 一个服务器发送事件流。每个SSE `data` 字段包含一个 `SendStreamingMessageResponse`。

### 7.10. `agent/getAuthenticatedExtendedCard`

在客户端认证后，检索可能更详细的代理卡版本。此端点仅在`AgentCard.supportsAuthenticatedExtendedCard`为`true`时可用。

  * **URL:** `agent/getAuthenticatedExtendedCard`
  * **HTTP 方法:** `POST`
  * **负载:** 无
  * **响应:** `AgentCard`

## 8\. 错误处理

A2A 使用标准的 [JSON-RPC 2.0 错误对象](https://www.jsonrpc.org/specification#error_object) 结构和代码来报告错误。错误在 `JSONRPCErrorResponse` 对象的 `error` 成员中返回。

### 8.1. 标准 JSON-RPC 错误

| 代码 | JSON-RPC 规范含义 | 典型的 A2A `message` | 描述 |
| :--- | :--- | :--- | :--- |
| -32700 | 解析错误 | 无效的 JSON 负载 | 服务器收到的 JSON 格式不正确。 |
| -32600 | 无效请求 | 无效的 JSON-RPC 请求 | JSON 负载是有效的 JSON，但不是有效的 JSON-RPC 请求对象。 |
| -32601 | 方法未找到 | 方法未找到 | 请求的 A2A RPC `method` 不存在或不受支持。 |
| -32602 | 无效参数 | 无效的方法参数 | 为方法提供的 `params` 无效（例如，类型错误、缺少必需字段）。 |
| -32603 | 内部错误 | 内部服务器错误 | 服务器在处理过程中发生意外错误。 |
| -32000 到 -32099 | 服务器错误 | *（服务器定义）* | 为实现定义的服务器错误保留。A2A 特定错误使用此范围。 |

### 8.2. A2A 特定错误

| 代码 | 错误名称（概念性） | 典型的 `message` 字符串 | 描述 |
| :--- | :--- | :--- | :--- |
| -32001 | `TaskNotFoundError` | 任务未找到 | 指定的任务 `id` 不对应于现有或活动任务。 |
| -32002 | `TaskNotCancelableError` | 任务无法取消 | 尝试取消一个处于不可取消状态的任务。 |
| -32003 | `PushNotificationNotSupportedError` | 不支持推送通知 | 客户端尝试使用推送通知功能，但服务器代理不支持。 |
| -32004 | `UnsupportedOperationError` | 此操作不受支持 | 请求的操作或其特定方面不受此服务器代理实现支持。 |
| -32005 | `ContentTypeNotSupportedError` | 不兼容的内容类型 | 请求的 `message.parts` 中提供的媒体类型不受代理或特定技能支持。 |
| -32006 | `InvalidAgentResponseError` | 无效的代理响应类型 | 代理为请求的方法生成了无效的响应。 |
| -32007 | `AuthenticatedExtendedCardNotConfiguredError` | 未配置认证扩展卡 | 代理未配置认证扩展卡。 |

## 9\. 常见工作流与示例

本节提供了常见A2A交互的JSON示例。

### 9.1. 获取认证扩展代理卡

...

### 9.2. 基本执行（同步/轮询风格）

...

### 9.3. 流式任务执行 (SSE)

...

### 9.4. 多轮交互 (需要输入)

...

### 9.5. 推送通知设置与使用

...

### 9.6. 文件交换（上传与下载）

...

### 9.7. 结构化数据交换（请求与提供JSON）

...

*(为简洁起见，工作流示例的详细JSON内容已省略，它们与HTML中的内容相同)*

## 10\. 附录

### 10.1. 与 MCP (模型上下文协议) 的关系

A2A 和 MCP 是为代理系统的不同方面设计的互补协议：

  * **[模型上下文协议 (MCP)](https://modelcontextprotocol.io/):** 专注于标准化 AI 模型和代理如何连接和与**工具、API、数据源和其他外部资源**交互。
  * **Agent2Agent 协议 (A2A):** 专注于标准化独立的、通常不透明的**AI代理如何作为对等方相互通信和协作**。

### 10.2. 安全考虑摘要

  * **传输安全:** 始终在生产环境中使用HTTPS。
  * **认证:** 通过标准的HTTP机制处理。
  * **授权:** 服务器端根据认证身份的责任。
  * **推送通知安全:** Webhook URL验证和认证至关重要。
  * **输入验证:** 服务器必须严格验证所有RPC参数和数据内容。
  * **资源管理:** 实施速率限制和资源限制。
  * **数据隐私:** 遵守所有适用的隐私法规。

## 11\. A2A 合规性要求

本节定义了A2A合规实现的规范性要求。

### 11.1. 代理合规性

一个A2A合规的代理**必须**：

#### 11.1.1. 传输支持要求

  * 至少支持一种在[第3.2节](https://www.google.com/search?q=%2332-supported-transport-protocols)中定义的传输协议。
  * 提供一个有效的`AgentCard`。
  * 在`AgentCard`中准确声明所有支持的传输。

#### 11.1.2. 核心方法实现

**必须**通过至少一种支持的传输实现以下所有核心方法：

  * `message/send`
  * `tasks/get`
  * `tasks/cancel`

#### 11.1.3. 可选方法实现

**可以**实现其他可选方法，如`message/stream`, `tasks/resubscribe`等，并相应地在`AgentCard`中声明。

#### 11.1.4. 多传输合规性

如果支持多种传输，**必须**确保功能等效性、行为一致性，并遵循所有传输特定的要求和方法映射。

#### 11.1.5. 数据格式合规性

**必须**使用有效的JSON-RPC 2.0结构、A2A数据对象，并使用定义的错误代码。

### 11.2. 客户端合规性

一个A2A合规的客户端**必须**：

#### 11.2.1. 传输支持

  * 能够使用至少一种传输协议进行通信。
  * 能够解析和解释`AgentCard`文档。
  * 能够根据代理声明的能力选择合适的传输。

#### 11.2.2. 协议实现

  * 能够正确构造至少`message/send`和`tasks/get`方法的请求。
  * 能够正确处理所有定义的A2A错误代码。
  * 在与需要认证的代理交互时，支持至少一种认证方法。

#### 11.2.3. 可选客户端功能

客户端**可以**实现多传输支持、流式支持、推送通知处理和扩展代理卡等功能。

### 11.3. 合规性测试

实现**应该**通过以下方式验证合规性：

  * **传输互操作性测试**
  * **方法映射验证**
  * **错误处理验证**
  * **数据格式验证**
  * **多传输一致性验证**