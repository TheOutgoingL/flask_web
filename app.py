# coding=utf-8
from flask import Flask, request, jsonify, render_template, send_file
import socket
import requests
import dns.resolver
from flask_sqlalchemy import SQLAlchemy
import json
import os
from urllib.parse import quote_plus
# 导入NeoVis相关模块
from py2neo import Graph
from pyvis.network import Network
from collections import defaultdict

app = Flask(__name__)

# 配置数据库连接
# password = quote_plus('cnic@2023')
# app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:{password}@localhost:33333/flask_DNSInfo'
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:123456@localhost/flask_DNSInfo'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 定义数据库模型
class DomainQuery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(100), unique=True, nullable=False)
    data = db.Column(db.Text, nullable=False)

    def __init__(self, domain, data):
        self.domain = domain
        self.data = data

@app.route('/')
def hello_world():
    """
    主页路由
    功能：返回主页面模板
    调用方法：GET /
    返回：渲染的index_split.html模板
    """
    return render_template("index_split.html")

@app.route('/split/')
def index_split():
    """
    分割页面路由
    功能：返回分割页面模板
    调用方法：GET /split/
    返回：渲染的index_split.html模板
    """
    return render_template("index_split.html")

@app.route('/dns_visualization/')
def dns_visualization():
    """
    DNS可视化页面路由
    功能：返回DNS可视化页面模板
    调用方法：GET /dns_visualization/
    返回：渲染的dns_visualization.html模板
    """
    return render_template("dns_visualization.html")

@app.route('/dns_query')
def dns_query():
    """
    DNS查询页面路由
    功能：返回DNS查询可视化页面，可接收域名参数
    调用方法：GET /dns_query?domain=example.com
    参数：domain - 要查询的域名（可选）
    返回：渲染的dns_query_visualization.html模板，传入域名参数
    """
    domain = request.args.get('domain', '')
    return render_template("dns_query_visualization.html", domain=domain)

@app.route('/dns_query_data')
def dns_query_data():
    """
    DNS查询数据API
    功能：执行DNS解析并返回解析日志数据
    调用方法：GET /dns_query_data?domain=example.com
    参数：domain - 要查询的域名（必需）
    返回：JSON格式的DNS解析日志数据或错误信息
    """
    domain = request.args.get('domain')
    if not domain:
        return jsonify({"error": "请提供域名参数"}), 400
    
    # 设置日志记录器
    import dns_query_log
    logger = dns_query_log.setup_logger(domain)
    
    # 创建DNS解析器并执行解析
    resolver = dns_query_log.LoggingDNSResolver(logger)
    resolver.db.ns_records['.'] = ['a.root-servers.net']
    
    # 执行DNS解析
    resolver.domain_dependency_resolution(domain)
    resolver.output_result(domain)
    
    # 读取生成的日志文件
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, f"{domain}_log.json")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            dns_data = json.load(f)
        return jsonify(dns_data)
    except Exception as e:
        return jsonify({"error": f"解析域名失败: {str(e)}"}), 500

@app.route('/network_only', methods=['GET'])
def network_only():
    """
    网络可视化图页面路由
    功能：返回只包含网络可视化图的页面
    调用方法：GET /network_only?domain=example.com
    参数：domain - 要可视化的域名（可选）
    返回：渲染的network_only.html模板，可传入域名参数
    """
    domain = request.args.get('domain')
    if domain:
        return render_template("network_only.html", domain=domain)
    else:
        return render_template("network_only.html")

@app.route('/query', methods=['POST'])
def query():
    """
    域名查询API
    功能：查询域名信息，支持通配符查询和普通查询
    调用方法：POST /query
    请求体：JSON格式 {"domain": "example.com"} 或 {"domain": "*.example.com"}
    返回：JSON格式的域名信息或子域名列表
    """
    data = request.json
    domain = data.get('domain')
    print(f"Received domain: {domain}")  # 打印接收到的数据

    if domain.startswith("*."):
        # Wildcard query
        base_domain = domain[2:]
        return query_wildcard(base_domain)
    else:
        # Regular query
        return query_domain(domain)

def query_domain(domain):
    """
    查询单个域名信息
    功能：从数据库查询域名信息，如不存在则执行DNS查询并存储
    参数：domain - 要查询的域名
    返回：JSON格式的域名信息
    """
    # 检查数据库中是否已经存在该域名的记录
    existing_query = DomainQuery.query.filter_by(domain=domain).first()
    if existing_query:
        print(f"Domain {domain} found in database.")
        # 如果存在，直接返回存储的 JSON 数据
        print(existing_query.data)
        return jsonify(json.loads(existing_query.data))
    else:
        print(f"Domain {domain} not found in database. Now lookup...")
        # 如果不存在，则执行查询
        domain_info = clean_data(get_domainInfo(domain))
        print(domain_info)

        # 将数据存储到数据库
        domain_info_json = json.dumps(domain_info)
        new_query = DomainQuery(domain=domain, data=domain_info_json)
        db.session.add(new_query)
        db.session.commit()

        return jsonify(domain_info)
def get_familyDomain(domain):
    """
    获取域名的家族域名列表
    功能：将域名分解为各级父域名
    参数：domain - 输入域名
    返回：包含各级父域名的列表
    示例：输入"www.example.com"返回["example.com", "com"]
    """
    segments = domain.split(".")
    family_domain = []
    #  输出segments列表的大小
    # print(len(segments))
    for i in range(len(segments), 1, -1):
        try_domain = ".".join(segments[len(segments) - i:])
        # print(try_domain)
        family_domain.append(try_domain)
    # 去除第一个元素
    # family_domain = family_domain[0:]
    print(family_domain)
    return  family_domain

def query_wildcard(base_domain):
    """
    通配符域名查询
    功能：查询数据库中所有匹配基域的子域名信息
    参数：base_domain - 基础域名
    返回：JSON格式的子域名信息列表
    """
    # 获取与基域匹配的所有子域
    subdomain_queries = DomainQuery.query.filter(DomainQuery.domain.like(f"%.{base_domain}")).all()
    print(subdomain_queries)
    res_list = [json.loads(query.data) for query in subdomain_queries]
    print(res_list)
    return jsonify(res_list)

@app.route('/server-count', methods=['GET'])
def server_count():
    """
    服务器计数API
    功能：返回数据库中域名查询记录的总数
    调用方法：GET /server-count
    返回：JSON格式的计数信息 {"count": 数量}
    """
    count = DomainQuery.query.count()
    return jsonify({'count': count})

@app.route('/test/')
def test():
    """http://127.0.0.1:50005/node/association-graph?domain=dns2.cdn20.info
    测试页面路由
    功能：返回测试页面模板
    调用方法：GET /test/
    返回：渲染的test.html模板
    """
    return render_template("test.html")

@app.route('/index000/')
def index000():
    """
    索引000页面路由
    功能：返回index000页面模板
    调用方法：GET /index000/
    返回：渲染的index000.html模板
    """
    return render_template("index000.html")

@app.route('/index/')
def index():
    """
    索引页面路由
    功能：返回index页面模板
    调用方法：GET /index/
    返回：渲染的index.html模板
    """
    return render_template("index.html")

@app.route('/domain-graph/<domain>', methods=['GET'])
def domain_graph(domain):
    """
    域名解析图页面路由
    功能：接收域名参数并展示该域名的解析图，如数据库中不存在则先查询并存储
    调用方法：GET /domain-graph/example.com
    参数：domain - URL路径中的域名
    返回：渲染的index_split.html模板，传入域名参数
    """
    # 检查数据库中是否已经存在该域名的记录
    existing_query = DomainQuery.query.filter_by(domain=domain).first()
    if not existing_query:
        # 如果不存在，则执行查询并存储
        domain_info = clean_data(get_domainInfo(domain))
        domain_info_json = json.dumps(domain_info)
        new_query = DomainQuery(domain=domain, data=domain_info_json)
        db.session.add(new_query)
        db.session.commit()
    
    # 返回展示页面，并传递域名参数
    return render_template("index_split.html", domain=domain)

@app.route('/api/domain-graph-url', methods=['GET'])
def get_domain_graph_url():
    """
    域名解析图URL生成API
    功能：根据提供的域名生成对应的解析图URL
    调用方法：GET /api/domain-graph-url?domain=example.com
    参数：domain - 要生成URL的域名（必需）
    返回：JSON格式的URL信息，包含成功状态、域名、URL和提示信息
    """
    domain = request.args.get('domain')
    if not domain:
        return jsonify({"error": "缺少域名参数"}), 400
    
    # 构建完整的URL，包括协议和主机名
    host = request.host
    url = f"http://{host}/domain-graph/{domain}"
    
    return jsonify({
        "success": True,
        "domain": domain,
        "url": url,
        "message": "点击URL查看域名解析图"
    })

def connect_to_neo4j():
    """
    连接Neo4j数据库
    功能：建立与Neo4j数据库的连接
    返回：Graph对象（成功）或None（失败）
    """
    try:
        graph = Graph("bolt://localhost:7687", auth=("neo4j", "liu2568910969"))
        print("成功连接到Neo4j数据库")
        return graph
    except Exception as e:
        print(f"连接Neo4j数据库失败: {e}")
        return None

def query_ns_graph(graph, domain):
    """
    查询Neo4j中的域名关联图谱数据
    功能：在Neo4j数据库中查询指定域名的关联路径
    参数：
        graph - Neo4j图数据库连接对象
        domain - 要查询的域名
    返回：查询结果列表，包含域名的关联路径数据
    """
    # 定义查询函数
    def execute_query(domain_name):
        query = f"""
        MATCH path = (n {{name: '{domain_name}'}})-[r*1..3]-(m)
        WHERE 'CNAME' IN labels(m) OR 'DNS' IN labels(m)
        RETURN path as r
        LIMIT 200
        """
        try:
            result = graph.run(query).data()
            print(f"查询到 {len(result)} 条记录")
            return result
        except Exception as e:
            print(f"查询失败: {e}")
            return []

    # 首次使用原始域名查询
    result = execute_query(domain)
    
    # 如果结果为空且域名不包含"."，尝试添加"."后再次查询
    if not result and domain[-1] != ".":
        domain_with_dot = domain + "."
        print(f"首次查询无结果，尝试使用 {domain_with_dot} 进行查询")
        result = execute_query(domain_with_dot)
    
    return result

def process_neo_graph_data(data, domain):
    """
    处理Neo4j图谱数据，转换为前端可用的格式
    功能：将Neo4j查询结果转换为vis.js可以使用的节点和边数据
    参数：
        data - Neo4j查询返回的图谱数据
        domain - 查询的域名
    返回：包含nodes和edges的字典
    """
    from collections import defaultdict
    import json
    
    # 存储节点和边
    nodes = {}
    edges = []
    node_connections = defaultdict(int)
    color_map = {}
    color_list = ["#FF5733", "#33FF57", "#3357FF", "#F39C12", "#9B59B6", "#1ABC9C", "#E74C3C"]
    color_index = 0
    edges_added = set()
    
    # 第一次遍历：统计每个节点的连接数和收集节点信息
    for record in data:
        paths = record["r"]
        for path in paths:
            start_node = path.start_node
            end_node = path.end_node
            start_id = str(start_node.identity)
            end_id = str(end_node.identity)
            
            # 增加节点连接计数
            node_connections[start_id] += 1
            node_connections[end_id] += 1
            
            # 收集节点信息
            for node in [start_node, end_node]:
                node_id = str(node.identity)
                if node_id not in nodes:
                    node_label = list(node.labels)[0] if node.labels else "Undefined"
                    node_name = node.get("name", node_label)
                    
                    # 为节点类型分配颜色
                    if node_label not in color_map:
                        color_map[node_label] = color_list[color_index % len(color_list)]
                        color_index += 1
                    
                    nodes[node_id] = {
                        "id": node_id,
                        "label": node_name,
                        "title": f"{node_name}\n类型: {node_label}\n属性: {dict(node)}",
                        "color": color_map[node_label],
                        "type": node_label,
                        "properties": dict(node)
                    }
            
            # 收集边信息
            edge_key = (start_id, end_id)
            if edge_key not in edges_added:
                edges.append({
                    "from": start_id,
                    "to": end_id,
                    "label": path.__class__.__name__,
                    "arrows": "to"
                })
                edges_added.add(edge_key)
    
    # 计算节点大小
    min_connections = 1
    max_connections = max(node_connections.values()) if node_connections else 1
    
    # 为节点添加大小信息
    for node_id, node in nodes.items():
        connection_count = node_connections[node_id]
        node_size = 15 + (connection_count - min_connections) * 35 / (max_connections - min_connections) if max_connections > min_connections else 20
        node["size"] = node_size
        node["title"] += f"\n连接数: {connection_count}"
    
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "color_map": color_map,
        "domain": domain
    }

def visualize_neo_graph(data, domain, output_file):
    """
    使用pyvis生成Neo4j关联图谱HTML
    功能：将Neo4j查询结果转换为可视化的网络图谱HTML文件
    参数：
        data - Neo4j查询返回的图谱数据
        domain - 查询的域名
        output_file - 输出HTML文件路径
    返回：无（生成HTML文件到指定路径）
    """
    net = Network(height="800px", width="100%", directed=True, notebook=False)
    net.force_atlas_2based(gravity=-30, central_gravity=0.05, spring_length=70, spring_strength=0.1)

    # 存储节点颜色和连接数
    node_colors = {}
    node_connections = defaultdict(int)  # 用于统计每个节点的连接数
    color_map = {}
    color_list = ["#FF5733", "#33FF57", "#3357FF", "#F39C12", "#9B59B6", "#1ABC9C", "#E74C3C"]
    color_index = 0
    edges_added = set()

    # 第一次遍历：统计每个节点的连接数
    for record in data:
        paths = record["r"]
        for path in paths:
            start_node = path.start_node
            end_node = path.end_node
            start_id = str(start_node.identity)
            end_id = str(end_node.identity)
            
            # 增加节点连接计数
            node_connections[start_id] += 1
            node_connections[end_id] += 1
            
            # 记录节点颜色
            for node in [start_node, end_node]:
                node_id = str(node.identity)
                node_label = list(node.labels)[0] if node.labels else "Undefined"
                
                if node_label not in color_map:
                    color_map[node_label] = color_list[color_index % len(color_list)]
                    color_index += 1
                    
                node_colors[node_id] = color_map[node_label]
    
    # 计算节点大小的最大值和最小值
    min_connections = 1
    max_connections = max(node_connections.values()) if node_connections else 1
    
    # 第二次遍历：添加节点和边
    added_nodes = set()
    for record in data:
        paths = record["r"]
        for path in paths:
            start_node = path.start_node
            end_node = path.end_node
            start_id = str(start_node.identity)
            end_id = str(end_node.identity)
            
            # 添加节点（如果尚未添加）
            for node in [start_node, end_node]:
                node_id = str(node.identity)
                if node_id not in added_nodes:
                    node_label = list(node.labels)[0] if node.labels else "Undefined"
                    node_name = node.get("name", node_label)
                    
                    # 根据连接数动态调整节点大小（最小15，最大50）
                    connection_count = node_connections[node_id]
                    node_size = 15 + (connection_count - min_connections) * 35 / (max_connections - min_connections) if max_connections > min_connections else 20
                    
                    # 不在外部显示标签，而是在节点内部展示
                    net.add_node(
                        node_id,
                        title=f"{node_name}\n连接数: {connection_count}\n{str(dict(node))}",  # 鼠标悬浮显示属性和连接数
                        color=node_colors[node_id],
                        size=node_size,  # 动态节点大小
                        label=node_name,
                        shape="dot",  # 使用圆形节点以便更好地显示内部标签
                        font={"size": 10, "color": "black", "face": "Arial", "strokeWidth": 0},  # 减小字体大小并移除描边
                        distance=100,
                    )
                    added_nodes.add(node_id)
            
            # 避免重复边
            edge_key = (start_id, end_id)
            if edge_key not in edges_added:
                net.add_edge(start_id, end_id, label=path.__class__.__name__, color="#A5ABB6",
                arrows={"to": {"enabled": True, "scaleFactor": 0.5}},  # 缩小箭头大小为默认值的一半
                font={"size": 10, "color": "#A5ABB6"}  # 边的文字样式
                )
                edges_added.add(edge_key)
                
    # 修改网络图的CSS样式以为图例留出空间
    net.set_options("""
    var options = {
      "physics": {
        "enabled": true,
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 20,
          "springConstant": 0.08,
          "damping": 0.4,
          "avoidOverlap": 0
        },
        "stabilization": {"enabled": true, "iterations": 150}
      }
    }
    """)
    
    # 生成HTML文件，确保使用绝对路径
    abs_output_file = output_file
    net.write_html(abs_output_file, notebook=False)
    
    # 读取生成的HTML文件并添加图例
    with open(abs_output_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 添加图例的CSS样式
    legend_css = """
    <style>
        body {
            margin: 0;
            padding: 0;
            display: flex;
            height: 100vh;
            overflow: hidden;
        }
        #legend {
            width: 300px;
            min-width: 300px;
            height: 100vh;
            padding: 20px;
            background-color: #f9f9f9;
            border-right: 1px solid #ddd;
            overflow-y: auto;
            box-sizing: border-box;
            flex-shrink: 0;
        }
        #mynetwork {
            flex: 1;
            height: 100vh !important;
            border: none !important;
            margin: 0 !important;
        }
        .card {
            flex: 1;
            height: 100vh;
            margin: 0 !important;
            border: none !important;
            display: flex;
            flex-direction: column;
        }
        .card-body {
            flex: 1;
            padding: 0 !important;
        }
        table.legendTable {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        .legendTable th, .legendTable td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .legendTable th {
            background-color: #f2f2f2;
        }
        .color-box {
            width: 20px;
            height: 20px;
            display: inline-block;
            border-radius: 3px;
            margin-right: 5px;
            vertical-align: middle;
        }
        h2 {
            margin-top: 0;
            color: #333;
        }
    </style>
    """
    
    # 创建图例HTML
    legend_html = f"""
    <div id="legend">
        <h2>节点类型图例</h2>
        <table class="legendTable">
            <tr>
                <th>颜色</th>
                <th>节点类型</th>
            </tr>
    """
    
    # 为每种节点类型添加一行
    for label, color in color_map.items():
        legend_html += f"""
            <tr>
                <td><span class="color-box" style="background-color: {color};"></span></td>
                <td>{label}</td>
            </tr>
        """
    
    legend_html += f"""
        </table>
        <div style="margin-top: 20px;">
            <h3>查询信息</h3>
            <p><strong>域名:</strong> {domain}</p>
        </div>
    </div>
    """
    
    # 在head中插入CSS
    html_content = html_content.replace('</head>', legend_css + '</head>')
    
    # 在body开始后插入图例
    html_content = html_content.replace('<body>', '<body>' + legend_html)
    
    # 重新写入文件
    with open(abs_output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"图谱已保存为 {abs_output_file}")

@app.route('/node/association-graph', methods=['GET'])
def get_association_graph():
    """
    Neo4j域名关联图谱API
    功能：从Neo4j数据库查询域名关联数据并生成可视化图谱
    调用方法：GET /node/association-graph?domain=example.com
    参数：domain - 要查询关联图谱的域名（必需）
    返回：渲染的neo-association.html模板页面或错误信息
    """
    domain = request.args.get('domain')
    if not domain:
        return render_template('error.html', 
                             title='参数错误', 
                             message='请提供域名参数', 
                             detail='例如: /node/association-graph?domain=example.com')
    
    try:
        # 连接Neo4j数据库
        graph = connect_to_neo4j()
        if not graph:
            return render_template('error.html', 
                                 title='数据库连接错误', 
                                 message='无法连接到Neo4j数据库')
        
        # 查询图谱数据
        data = query_ns_graph(graph, domain)
        
        if not data:
            return render_template('error.html', 
                                 title='数据未找到', 
                                 message=f'未找到域名 {domain} 的关联数据', 
                                 detail='请检查域名是否正确或数据库中是否存在相关数据。')
        
        # 处理图谱数据，转换为前端可用的格式
        graph_data = process_neo_graph_data(data, domain)
        
        # 使用render_template返回模板，传递图谱数据
        return render_template('neo-association.html', 
                             domain=domain, 
                             graph_data=graph_data)
        
    except Exception as e:
        print(f"获取关联数据失败: {e}")
        return render_template('error.html', 
                             title='获取关联数据失败', 
                             message='服务器内部错误', 
                             detail=str(e))


@app.errorhandler(404)
def page_not_found(e):
    """
    404错误处理器
    功能：处理页面未找到的错误
    返回：404错误信息
    """
    return 'This page does not exist.', 404

def getCNAME(domain_name):
    """
    获取域名的CNAME记录
    功能：查询指定域名的CNAME记录
    参数：domain_name - 要查询的域名
    返回：CNAME记录字符串（去除末尾点号）或None（查询失败）
    """
    try:
        resolver = dns.resolver.Resolver()
        ans = resolver.resolve(domain_name, 'CNAME')
        for rdata in ans:
            cname = str(rdata)
            return cname[:-1]
    except Exception as e:
        print(f"Error getting CNAME for {domain_name}: {e}")
        return None

def get_all_ips(domain):
    """
    获取域名的所有A记录IP地址
    功能：查询指定域名的所有A记录，返回IP地址列表
    参数：domain - 要查询的域名
    返回：IP地址字符串列表，查询失败返回空列表
    """
    try:
        answers = dns.resolver.resolve(domain, 'A')
        ips = [str(rdata) for rdata in answers]
        return ips
    except dns.resolver.NoAnswer:
        print(f"无法找到域名 {domain} 的IP地址")
        return []

# def get_ip_info(ip):
#     try:
#         # 调用淘宝IP API
#         response = requests.get(f"https://ip.taobao.com/outGetIpInfo?accessKey=alibaba-inc&ip={ip}")
#         if response.status_code == 200:
#             data = response.json()
#             if data.get("code") == 0:  # 检查返回的code是否为0表示成功
#                 ip_data = data.get("data", {})

#                 # 将空字符串替换为"未知"
#                 def replace_unknown(value):
#                     return "未知" if value == "" or value is None else value

#                 return {
#                     "ip": ip,
#                     "country": replace_unknown(ip_data.get("country", "未知")),
#                     "isp": replace_unknown(ip_data.get("isp", "未知"))
#                 }
#             else:
#                 print(f"未能成功获取IP信息: {data}")
#                 return {"ip": ip, "country": "未知", "isp": "未知"}
#         else:
#             print(f"获取IP信息失败，状态码: {response.status_code}")
#             return {"ip": ip, "country": "未知", "isp": "未知"}
#     except requests.RequestException as e:
#         print(f"请求过程中出现错误: {e}")
#         return {"ip": ip, "country": "未知", "isp": "未知"}
# # print(clean_data(get_domainInfo(domain)))
def get_ip_info(ip):
    """
    获取IP的详细信息（国家、ISP等）
    功能：通过ipplus360 API查询IP地址的地理位置和ISP信息
    参数：ip - 要查询的IP地址
    返回：包含IP、国家、ISP信息的字典，查询失败或ISP为空返回None
    """
    try:
        # 调用 ipplus360 API
        api_key = "fQf9F6JO0hW4wGA9SanmZ3Dh7OR6SFf2YUdDWPiZDY5pGkVtIMw9HNuFvMWquwyn"
        response = requests.get(f"https://api.ipplus360.com/ip/geo/v1/city/?key={api_key}&ip={ip}&coordsys=WGS84")
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "Success":
                ip_data = data.get("data", {})               
                # 获取ISP信息
                isp = ip_data.get("isp", "")
                # print(f"ISP: {isp}")
                # 如果ISP是空的，则不输出
                if not isp or isp == "":
                    return None
                # 将空字符串替换为"未知"
                def replace_unknown(value):
                    return "未知" if value == "" or value is None else value
                return {
                    "ip": ip,
                    "country": replace_unknown(ip_data.get("country", "未知")),
                    "isp": isp
                }
            else:
                print(f"未能成功获取IP: {ip}的信息: {data.get('msg', '未知错误')}")
                return None
        else:
            print(f"获取IP: {ip}信息失败，状态码: {response.status_code}")
            return None
    except Exception as e:
        print(f"请求过程中出现错误: {e}")
        return None

def get_ips_info(domain):
    """
    获取域名所有IP的详细信息
    功能：获取域名的所有IP地址，并查询每个IP的详细信息
    参数：domain - 要查询的域名
    返回：包含所有IP详细信息的列表
    """
    ips = get_all_ips(domain)
    ip_info_list = []
    for ip in ips:
        info = get_ip_info(ip)
        ip_info_list.append(info)
    return ip_info_list

def get_domainInfo(domain):
    """
    获取域名的完整信息
    功能：获取域名的DNS记录、NS记录、CNAME记录等完整信息
    参数：domain - 要查询的域名
    返回：包含域名完整信息的列表，每个元素包含[域名, CNAME, 家族域名, NS服务器, NS_IP, DNS_IP列表, 查找域名, IP信息列表]
    """
    domain_info = []
    ips_info = []
    ip_set = set()  # 用于存储已经处理过的IP

    DNS_IP = get_all_ips(domain)
    for ip in DNS_IP:
        if ip not in ip_set:
            ip_info = get_ip_info(ip)
            ips_info.append(ip_info)
            ip_set.add(ip)

    resolver = dns.resolver.Resolver()

    family_domains = get_familyDomain(domain)
    try:
        ans = resolver.resolve(domain, 'NS')
        for rdata in ans:
            ns = str(rdata)
            ns_ip = socket.gethostbyname(ns)
            if ns_ip not in ip_set:
                ip_info = get_ip_info(ns_ip)
                ips_info.append(ip_info)
                ip_set.add(ns_ip)
            domain_info.append([domain, "null", family_domains, ns, ns_ip, DNS_IP, domain, ips_info])
    except:
        CNAME = getCNAME(domain)
        if CNAME:
            family_domains_cname = get_familyDomain(CNAME)
            for family_domain_cname in family_domains_cname:
                try:
                    ans = resolver.resolve(family_domain_cname, 'NS')
                    ns_records = []
                    for rdata in ans:
                        ns = str(rdata)
                        ns_ip = socket.gethostbyname(ns)
                        if ns_ip not in ip_set:
                            ip_info = get_ip_info(ns_ip)
                            ips_info.append(ip_info)
                            ip_set.add(ns_ip)
                        ns_records.append((ns, ns_ip))
                    for ns, ns_ip in ns_records:
                        domain_info.append([domain, CNAME, family_domains, ns, ns_ip, DNS_IP, family_domain_cname, ips_info])
                    break
                except:
                    pass
        else:
            for family_domain in family_domains:
                try:
                    ans = resolver.resolve(family_domain, 'NS')
                    for rdata in ans:
                        ns = str(rdata)
                        ns_ip = socket.gethostbyname(ns)
                        if ns_ip not in ip_set:
                            ip_info = get_ip_info(ns_ip)
                            ips_info.append(ip_info)
                            ip_set.add(ns_ip)
                        domain_info.append([domain, "null", family_domains, ns, ns_ip, DNS_IP, family_domain, ips_info])
                    break
                except:
                    pass
    return domain_info

def clean_data(domain_info):
    """
    清理和整理域名信息数据
    功能：将get_domainInfo返回的原始数据整理成结构化的字典格式
    参数：domain_info - get_domainInfo函数返回的原始域名信息列表
    返回：包含DNS、CNAME、家族域名、权威DNS、IP信息等的结构化字典
    """
    dns_set = set()
    cname_set = set()
    family_domains_list = []
    auth_dns_list = []
    auth_ip_list = []
    dns_ip_set = set()
    find_by_dns_set = set()
    ips_info_list = []

    for record in domain_info:
        dns_set.add(record[0])
        cname_set.add(record[1])
        family_domains_list.append(record[2])

        if record[3] not in auth_dns_list:
            auth_dns_list.append(record[3])
            auth_ip_list.append(record[4])

        dns_ip_set.update(record[5])
        find_by_dns_set.add(record[6])

        # 将记录中的ips_info（第8项）添加到ips_info_list，且仅添加不重复的IP信息
        for ip_info in record[7]:
            ips_info_list.append(ip_info)
            # dns_ip_set.add(ip_info["ip"])

    domain_info_dict = {
        'DNS': list(dns_set),
        'CNAME': list(cname_set),
        'Family_Domains': sorted(family_domains_list,key=lambda domain: domain.count('.'))[0],
        'Auth_DNS': auth_dns_list,
        'Auth_IP': auth_ip_list,
        'DNS_IP': list(dns_ip_set),
        'FindBy_DNS': list(find_by_dns_set),
        'IP_Info': ips_info_list  # 包含所有IP和NS IP的国家和ISP信息
    }
    return domain_info_dict

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # 创建所有表
    app.run(host="0.0.0.0", port=50005, debug=True)
