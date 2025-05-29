# coding=utf-8
from flask import Flask, request, jsonify, render_template
import socket
import requests
import dns.resolver
from flask_sqlalchemy import SQLAlchemy
import json
import os
from urllib.parse import quote_plus

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
    return render_template("index_split.html")

@app.route('/split/')
def index_split():
    return render_template("index_split.html")

@app.route('/dns_visualization/')
def dns_visualization():
    return render_template("dns_visualization.html")

@app.route('/dns_query')
def dns_query():
    domain = request.args.get('domain', '')
    return render_template("dns_query_visualization.html", domain=domain)

@app.route('/dns_query_data')
def dns_query_data():
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

# 新增API端点，只返回网络可视化图的内容
@app.route('/network_only', methods=['GET'])
def network_only():
    domain = request.args.get('domain')
    if domain:
        return render_template("network_only.html", domain=domain)
    else:
        return render_template("network_only.html")

@app.route('/query', methods=['POST'])
def query():
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
    # 获取与基域匹配的所有子域
    subdomain_queries = DomainQuery.query.filter(DomainQuery.domain.like(f"%.{base_domain}")).all()
    print(subdomain_queries)
    res_list = [json.loads(query.data) for query in subdomain_queries]
    print(res_list)
    return jsonify(res_list)

@app.route('/server-count', methods=['GET'])
def server_count():
    count = DomainQuery.query.count()
    return jsonify({'count': count})

@app.route('/test/')
def test():
    return render_template("test.html")

@app.route('/index000/')
def index000():
    return render_template("index000.html")

@app.route('/index/')
def index():
    return render_template("index.html")

@app.route('/domain-graph/<domain>', methods=['GET'])
def domain_graph(domain):
    """接收域名参数并展示该域名的解析图"""
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
    """提供一个API接口，返回域名解析图的URL"""
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

@app.errorhandler(404)
def page_not_found(e):
    return 'This page does not exist.', 404

def getCNAME(domain_name):
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
    """获取IP的详细信息（国家、ISP等）"""
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
    ips = get_all_ips(domain)
    ip_info_list = []
    for ip in ips:
        info = get_ip_info(ip)
        ip_info_list.append(info)
    return ip_info_list

def get_domainInfo(domain):
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
