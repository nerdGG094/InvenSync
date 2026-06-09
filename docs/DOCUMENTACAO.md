# 📦 InvenSync — Documentação Técnica

> Sistema de controle de almoxarifado de **TI** (toner, cilindros, periféricos, peças e ativos)
> da **Refrigerantes Jaboti**. Aplicação web em **Flask** com banco **PostgreSQL**, servida em
> produção via **waitress** e gerenciada por um **launcher** desktop (PyQt5).

| | |
|---|---|
| **Nome** | InvenSync |
| **Domínio** | Almoxarifado de TI |
| **Stack** | Python 3.12 · Flask 3 · SQLAlchemy 2 · PostgreSQL 17 · Bootstrap 5 |
| **Servidor** | waitress (produção) / run.py (dev) |
| **Repositório** | https://github.com/nerdGG094/InvenSync |

---

## 1. Visão Geral

O InvenSync controla o estoque do setor de TI, com cadastro de produtos (com campos específicos
como marca, modelo, patrimônio, número de série, localização, compatibilidade e validade),
fornecedores, categorias, e o registro de **movimentações** de entrada e saída. Possui painel com
indicadores, board **Kanban** de saúde de estoque, relatórios, exportação CSV e gestão de usuários
com controle de acesso (ativo/inativo).

### Tecnologias

```mermaid
mindmap
  root((InvenSync))
    Backend
      Python 3.12
      Flask 3
      Flask-Login
      Flask-WTF
      SQLAlchemy 2
      psycopg 3
    Banco
      PostgreSQL 17
      Banco inventario_almox
    Frontend
      Jinja2
      Bootstrap 5.3
      Bootstrap Icons
      Chart.js
    Operação
      waitress
      Launcher PyQt5
      python-dotenv
```

---

## 2. Arquitetura em Camadas

A aplicação segue uma arquitetura em camadas (layered), separando apresentação, regras de acesso a
dados e domínio.

```mermaid
flowchart TB
    subgraph CLIENT["🌐 Cliente"]
        BROWSER["Navegador / Celular / Tablet"]
    end

    subgraph APP["🐍 Aplicação Flask (create_app)"]
        direction TB
        ROUTES["Camada de Rotas (Blueprints)<br/>auth · dashboard · products · categories<br/>suppliers · movements · reports · users · kanban · health"]
        FORMS["Formulários (Flask-WTF)<br/>validação de entrada"]
        SERVICES["Serviços<br/>inventory_service"]
        REPOS["Repositórios<br/>product · category · supplier · movement"]
        MODELS["Modelos (SQLAlchemy ORM)<br/>User · Category · Supplier · Product · StockMovement"]
        EXT["Extensões<br/>db · login_manager"]
    end

    subgraph DATA["🗄️ Persistência"]
        PG[("PostgreSQL 17<br/>inventario_almox")]
    end

    BROWSER -->|HTTP| ROUTES
    ROUTES --> FORMS
    ROUTES --> SERVICES
    ROUTES --> REPOS
    SERVICES --> REPOS
    REPOS --> MODELS
    MODELS --> EXT
    EXT -->|SQL via psycopg| PG
```

---

## 3. Modelo de Dados (Diagrama Entidade-Relacionamento)

```mermaid
erDiagram
    USER ||--o{ STOCK_MOVEMENT : "registra"
    CATEGORY ||--o{ PRODUCT : "classifica"
    SUPPLIER ||--o{ PRODUCT : "fornece"
    PRODUCT ||--o{ STOCK_MOVEMENT : "movimenta"

    USER {
        int id PK
        string name
        string email UK "índice único"
        string password_hash
        bool is_admin
        bool is_active "bloqueia login se falso"
    }

    CATEGORY {
        int id PK
        string name UK
        text description
    }

    SUPPLIER {
        int id PK
        string name UK
        string email
        string phone
        text notes
    }

    PRODUCT {
        int id PK
        string sku UK "PREFIXO-0001 (auto)"
        string name
        text description
        string item_type "product/raw_material/kit/service"
        string unit "UN, CX, KG..."
        int category_id FK
        int supplier_id FK
        int min_stock
        decimal price
        datetime created_at
        string brand "Marca - TI"
        string model "Modelo - TI"
        string patrimony "Patrimônio - TI"
        string serial_number "Nº Série - TI"
        string location "Localização - TI"
        text compatibility "Compatibilidade - TI"
        date expiry_date "Validade - TI"
    }

    STOCK_MOVEMENT {
        int id PK
        int product_id FK
        string movement_type "IN / OUT"
        int quantity
        decimal unit_cost
        text note
        datetime created_at
        int user_id FK
    }
```

### 3.1 Dicionário de Dados

#### Tabela `user`
| Campo | Tipo | Nulo | Descrição |
|---|---|---|---|
| id | integer (PK) | não | Identificador |
| name | varchar(120) | não | Nome do usuário |
| email | varchar(255) UK | não | E-mail (login), índice único |
| password_hash | varchar(255) | não | Hash da senha (scrypt) |
| is_admin | boolean | sim | Perfil administrador |
| is_active | boolean | não | Se inativo, não consegue logar |

#### Tabela `category`
| Campo | Tipo | Nulo | Descrição |
|---|---|---|---|
| id | integer (PK) | não | Identificador |
| name | varchar(120) UK | não | Nome único da categoria |
| description | text | sim | Descrição |

#### Tabela `supplier`
| Campo | Tipo | Nulo | Descrição |
|---|---|---|---|
| id | integer (PK) | não | Identificador |
| name | varchar(200) UK | não | Razão/nome único |
| email | varchar(255) | sim | Contato |
| phone | varchar(50) | sim | Telefone |
| notes | text | sim | Observações |

#### Tabela `product`
| Campo | Tipo | Nulo | Descrição |
|---|---|---|---|
| id | integer (PK) | não | Identificador |
| sku | varchar(120) UK | não | Código único (gerado `PREFIXO-0001`) |
| name | varchar(200) | não | Nome do item |
| description | text | sim | Descrição |
| item_type | varchar(20) | não | Tipo (product/raw_material/kit/service) |
| unit | varchar(10) | não | Unidade de medida (UN, CX, KG...) |
| category_id | integer (FK→category) | sim | Categoria |
| supplier_id | integer (FK→supplier) | sim | Fornecedor |
| min_stock | integer | sim | Estoque mínimo (alerta) |
| price | numeric(12,2) | sim | Preço |
| created_at | timestamp | sim | Data de criação |
| brand | varchar(120) | sim | **TI** — Marca (HP, Brother...) |
| model | varchar(120) | sim | **TI** — Modelo (TN-660...) |
| patrimony | varchar(60) | sim | **TI** — Nº de patrimônio |
| serial_number | varchar(120) | sim | **TI** — Nº de série |
| location | varchar(120) | sim | **TI** — Localização física |
| compatibility | text | sim | **TI** — Equipamentos compatíveis |
| expiry_date | date | sim | **TI** — Validade (toner/cilindro) |

#### Tabela `stock_movement`
| Campo | Tipo | Nulo | Descrição |
|---|---|---|---|
| id | integer (PK) | não | Identificador |
| product_id | integer (FK→product) | não | Produto movimentado |
| movement_type | varchar(3) | não | `IN` (entrada) ou `OUT` (saída) |
| quantity | integer | não | Quantidade |
| unit_cost | numeric(12,2) | sim | Custo unitário (entradas) |
| note | text | sim | Observação |
| created_at | timestamp | sim | Data/hora da movimentação |
| user_id | integer (FK→user) | sim | Quem registrou |

> **Saldo de estoque** = Σ(quantidade `IN`) − Σ(quantidade `OUT`) por produto.

---

## 4. Diagrama de Classes (UML)

```mermaid
classDiagram
    class User {
        +int id
        +str name
        +str email
        +str password_hash
        +bool is_admin
        +bool is_active
        +set_password(password)
        +check_password(password) bool
    }
    class Category {
        +int id
        +str name
        +str description
    }
    class Supplier {
        +int id
        +str name
        +str email
        +str phone
        +str notes
    }
    class Product {
        +int id
        +str sku
        +str name
        +str item_type
        +str unit
        +int min_stock
        +Decimal price
        +str brand
        +str model
        +str patrimony
        +str serial_number
        +str location
        +date expiry_date
    }
    class StockMovement {
        +int id
        +str movement_type
        +int quantity
        +Decimal unit_cost
        +datetime created_at
    }

    User "1" --> "0..*" StockMovement : registra
    Category "1" --> "0..*" Product : classifica
    Supplier "1" --> "0..*" Product : fornece
    Product "1" --> "0..*" StockMovement : possui
```

---

## 5. Diagrama de Implantação (Deployment)

```mermaid
flowchart TB
    subgraph SERVER["🖥️ Windows Server 2019 — 192.168.0.54"]
        subgraph LAUNCH["Launcher (PyQt5) — pythonw"]
            UI["Janela + Bandeja<br/>Iniciar / Parar / Reiniciar<br/>Teste /health"]
        end
        subgraph PROC["Processo do Servidor"]
            WAIT["serve.py<br/>waitress (8 threads)<br/>0.0.0.0:5090"]
            FLASK["Flask app (create_app)"]
        end
        ENVF[".env<br/>SECRET_KEY · credenciais DB"]
        PG[("PostgreSQL 17<br/>porta 5432<br/>inventario_almox")]
    end

    USERS["👥 Navegadores na rede<br/>(PC / celular / tablet)"]

    UI -->|"subprocess (stdout=logs)"| WAIT
    WAIT --> FLASK
    FLASK -->|"lê segredos"| ENVF
    FLASK -->|"psycopg / SQL"| PG
    USERS -->|"HTTP :5090"| WAIT

    START["Atalho na Inicialização do Windows"] -.->|"auto-start no login"| LAUNCH
```

---

## 6. Diagramas de Sequência

### 6.1 Login (com bloqueio de usuário inativo)

```mermaid
sequenceDiagram
    actor U as Usuário
    participant B as Navegador
    participant A as auth (rota)
    participant M as User (modelo)
    participant DB as PostgreSQL

    U->>B: preenche e-mail e senha
    B->>A: POST /login
    A->>M: User.query.filter_by(email)
    M->>DB: SELECT
    DB-->>M: usuário
    A->>M: check_password(senha)
    alt credenciais inválidas
        A-->>B: flash "Credenciais inválidas"
    else inativo (is_active = false)
        A-->>B: flash "Usuário desativado"
    else ok
        A->>A: login_user(user)
        A-->>B: redirect /dashboard
    end
```

### 6.2 Cadastro de Produto com SKU automático

```mermaid
sequenceDiagram
    actor U as Usuário
    participant B as Navegador
    participant JS as JS do formulário
    participant P as products (rota)
    participant R as product_repo
    participant DB as PostgreSQL

    U->>B: digita nome / escolhe tipo e categoria
    B->>JS: evento input/change (debounce 350ms)
    JS->>P: GET /products/suggest-sku?item_type&category_id
    P->>R: _sku_prefix() + _next_sku()
    R->>DB: SELECT max sequência do prefixo
    DB-->>R: maior número
    P-->>JS: { sku: "TON-0001" }
    JS-->>B: preenche o campo SKU

    U->>B: Salvar
    B->>P: POST /products/new
    loop até 6 tentativas (corrida)
        P->>R: create_product(...)
        R->>DB: INSERT
        alt SKU já existe (IntegrityError)
            DB-->>R: erro de unicidade
            P->>P: gera próximo SKU e tenta de novo
        else sucesso
            DB-->>R: ok
            P-->>B: redirect + flash "Produto criado! SKU: TON-0001"
        end
    end
```

### 6.3 Registro de Movimentação de Estoque

```mermaid
sequenceDiagram
    actor U as Usuário (logado)
    participant B as Navegador
    participant M as movements (rota)
    participant R as movement_repo
    participant DB as PostgreSQL

    U->>B: produto, tipo (IN/OUT), quantidade, custo
    B->>M: POST /movements
    M->>R: create_movement(product, type, qty, cost, note, user)
    R->>DB: INSERT stock_movement
    DB-->>R: ok
    M->>DB: agrega totais do filtro (SUM CASE)
    M-->>B: lista atualizada (cards + histórico)
```

---

## 7. Fluxogramas de Regras de Negócio

### 7.1 Geração do SKU

```mermaid
flowchart TD
    A["Início da geração"] --> B{"Categoria<br/>selecionada?"}
    B -->|Sim| C["prefixo = 3 letras da categoria<br/>(sem acento, maiúsculas)"]
    B -->|Não| D["prefixo = código do tipo<br/>PRD/INS/KIT/SRV"]
    C --> E["Busca maior sequência<br/>existente do prefixo"]
    D --> E
    E --> F["SKU = PREFIXO-(max+1) com 4 dígitos"]
    F --> G{"SKU já existe<br/>no banco?"}
    G -->|Sim| H["Incrementa e tenta de novo<br/>(até 6x)"]
    H --> G
    G -->|Não| I["✅ SKU final"]
```

### 7.2 Classificação do Kanban de Estoque

```mermaid
flowchart TD
    A["Saldo do produto<br/>(entradas − saídas)"] --> B{"saldo ≤ 0?"}
    B -->|Sim| C["🔴 Sem estoque"]
    B -->|Não| D{"saldo ≤ mínimo?"}
    D -->|Sim| E["🟡 Abaixo do mínimo"]
    D -->|Não| F{"saldo ≤ mínimo × 1,5?"}
    F -->|Sim| G["🔵 Atenção (margem curta)"]
    F -->|Não| H["🟢 Saudável"]
```

---

## 8. Diagramas de Estado

### 8.1 Servidor (visto pelo Launcher)

```mermaid
stateDiagram-v2
    [*] --> Parado
    Parado --> Iniciando : Iniciar
    Iniciando --> Rodando : processo no ar
    Iniciando --> Erro : falha ao subir
    Rodando --> Parando : Parar / Reiniciar
    Parando --> Parado : encerrado
    Rodando --> Erro : queda inesperada
    Erro --> Iniciando : Iniciar
    Parado --> [*]
```

### 8.2 Acesso do Usuário

```mermaid
stateDiagram-v2
    [*] --> Ativo
    Ativo --> Inativo : desativar (switch)
    Inativo --> Ativo : ativar (switch)
    Ativo --> Logado : login válido
    Logado --> Ativo : logout
    Inativo --> Inativo : login bloqueado
```

---

## 9. Casos de Uso

```mermaid
flowchart LR
    ADMIN(["👤 Administrador"])
    OPER(["👤 Operador de TI"])

    subgraph SISTEMA["InvenSync"]
        UC1["Gerenciar produtos"]
        UC2["Registrar movimentações"]
        UC3["Consultar Kanban / Dashboard"]
        UC4["Emitir relatórios / exportar CSV"]
        UC5["Gerenciar categorias e fornecedores"]
        UC6["Gerenciar usuários e acessos"]
        UC7["Ativar / desativar usuário"]
    end

    OPER --> UC1
    OPER --> UC2
    OPER --> UC3
    OPER --> UC4
    OPER --> UC5
    ADMIN --> UC1
    ADMIN --> UC6
    ADMIN --> UC7
    ADMIN --> UC4
```

---

## 10. Mapa de Rotas (Endpoints)

| Método | Rota | Blueprint | Descrição | Login |
|---|---|---|---|---|
| GET/POST | `/login` | auth | Autenticação | — |
| GET | `/logout` | auth | Encerrar sessão | — |
| GET | `/` | dashboard | Painel com indicadores e gráficos | ✅ |
| GET | `/products` | products | Lista de produtos | ✅ |
| GET/POST | `/products/new` | products | Cadastrar (SKU automático) | ✅ |
| GET/POST | `/products/<id>/edit` | products | Editar produto | ✅ |
| POST | `/products/<id>/delete` | products | Excluir produto | ✅ |
| GET | `/products/suggest-sku` | products | Sugerir próximo SKU (JSON) | ✅ |
| GET/POST | `/categories` … | categories | CRUD de categorias | ✅ |
| GET/POST | `/suppliers` … | suppliers | CRUD de fornecedores | ✅ |
| GET/POST | `/movements` | movements | Registrar e listar movimentações | ✅ |
| GET | `/reports/stock` | reports | Relatório de estoque | ✅ |
| GET | `/reports/export/products.csv` | reports | Exportar CSV | ✅ |
| GET | `/kanban` | kanban | Board de saúde de estoque | ✅ |
| GET/POST | `/users` … | users | Gestão de usuários (admin) | ✅ |
| POST | `/users/<id>/toggle-active` | users | Ativar/desativar usuário | ✅ |
| GET | `/health` | health | Status do serviço (JSON) | — |

---

## 11. Estrutura de Pastas

```text
InventarioAlmox/
├── inventory/                 # pacote da aplicação
│   ├── __init__.py            # create_app() — fábrica do app
│   ├── config.py              # configuração (lê .env)
│   ├── extensions.py          # db, login_manager
│   ├── models/                # ORM: user, category, supplier, product, movement
│   ├── repositories/          # acesso a dados por entidade
│   ├── services/              # regras de domínio (inventory_service)
│   ├── forms/                 # formulários Flask-WTF
│   ├── routes/                # blueprints (auth, products, ... , health)
│   ├── templates/             # Jinja2 (base + telas)
│   └── static/                # style.css, logo, favicon
├── docs/
│   └── DOCUMENTACAO.md        # este documento
├── setup/
│   ├── install.bat            # instala deps + atalhos (Desktop/Startup)
│   └── start_invensync.bat    # inicia o launcher (pythonw)
├── launcher.py                # painel desktop PyQt5
├── serve.py                   # servidor de produção (waitress)
├── run.py                     # servidor de desenvolvimento (Flask)
├── migrate_sqlite_to_pg.py    # migração única SQLite → PostgreSQL
├── requirements.txt
├── .env / .env.example        # segredos (não versionado / modelo)
└── README.md
```

---

## 12. Segurança e Configuração

```mermaid
flowchart LR
    ENV[".env (fora do Git)"] --> CFG["config.py"]
    CFG --> APP["create_app()"]
    subgraph SEC["Práticas"]
        S1["Senhas com hash scrypt"]
        S2["Segredos só no .env"]
        S3["Login obrigatório nas rotas"]
        S4["is_active bloqueia acesso"]
        S5["Admin não se autodesativa/exclui"]
    end
    APP --> SEC
```

- **Variáveis sensíveis** (`SECRET_KEY`, `DB_PASSWORD`, …) ficam no `.env`, fora do versionamento.
- **Senhas** armazenadas como hash (`werkzeug` / scrypt) — nunca em texto puro.
- **Acesso**: todas as telas exigem login; usuários **inativos** não logam.
- **Proteções de admin**: não é possível desativar nem excluir a própria conta.

---

## 13. Como Executar

### Produção (recomendado)
```bat
:: 1. Instala dependências e cria atalhos (Desktop + Inicialização)
setup\install.bat

:: 2. Inicia o painel (auto-sobe o servidor waitress)
setup\start_invensync.bat
```
Acesse: **http://192.168.0.54:5090**

### Desenvolvimento
```bat
.venv\Scripts\python run.py
```

### Migração inicial (uma vez)
```bat
.venv\Scripts\python migrate_sqlite_to_pg.py
```

---

> _Documentação gerada para o projeto InvenSync. Os diagramas usam **Mermaid** e são renderizados
> automaticamente no GitHub, VS Code (extensão Markdown Preview Mermaid) e demais visualizadores compatíveis._
