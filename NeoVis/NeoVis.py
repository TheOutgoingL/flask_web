from py2neo import Graph
from pyvis.network import Network
from collections import defaultdict
import os
import webbrowser

# 连接到 Neo4j 数据库
def connect_to_neo4j():
    try:
        graph = Graph("bolt://localhost:7687", auth=("neo4j", "liu2568910969"))
        print("成功连接到Neo4j数据库")
        return graph
    except Exception as e:
        print(f"连接Neo4j数据库失败: {e}")
        return None

# # 查询图谱数据
# def query_graph(graph, domain):
#     query = f"""
#     MATCH (n {{name: '{domain}'}})-[r*1..4]->(m)
#     RETURN n, r, m
#     LIMIT 500
#     """
#     try:
#         result = graph.run(query).data()
#         print(f"查询到 {len(result)} 条记录")
#         return result
#     except Exception as e:
#         print(f"查询失败: {e}")
#         return []
# 查询图谱数据
def query_ns_graph(graph, domain):
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

def visualize_graph(data, output_file="NeoSearch.html"):
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
    
    # 生成HTML文件
    net.write_html(output_file, notebook=False)
    
    # 读取生成的HTML文件并添加图例
    with open(output_file, 'r', encoding='utf-8') as f:
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
    legend_html = """
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
    
    legend_html += """
        </table>
    </div>
    """
    
    # 在head中插入CSS
    html_content = html_content.replace('</head>', legend_css + '</head>')
    
    # 在body开始后插入图例
    html_content = html_content.replace('<body>', '<body>' + legend_html)
    
    # 重新写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"图谱已保存为 {output_file}")
    
    # 使用默认浏览器打开生成的HTML文件
    file_path = os.path.abspath(output_file)
    print(f"正在打开图谱文件: {file_path}")
    webbrowser.open('file://' + file_path, new=2)  # new=2表示在新标签页打开

# 主程序
if __name__ == "__main__":
    domain = input("请输入要查询的域名：").strip()
    graph = connect_to_neo4j()
    if graph:
        # data = query_graph(graph, domain)
        data = query_ns_graph(graph, domain)
        if data:
            visualize_graph(data)
