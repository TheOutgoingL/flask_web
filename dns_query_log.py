# -*- coding: utf-8 -*-
import os
import sys
import logging
from datetime import datetime
import json
import dns.message
import dns.query
import dns.flags
import dns.rdatatype
import dns.resolver
import dns.exception
import time

class DNSDatabase:
    """数据库结构：存放各级 NS、glue、CNAME、A 记录以及父域关系和查询过程记录"""
    def __init__(self):
        # zone -> NS 记录列表，例如：'com' : ['ns1.comdns.net', 'ns2.comdns.net']
        self.ns_records = {}
        # glue 记录：NS 主机名 -> { 'A': [ip列表], 'AAAA': [ip列表] }
        self.glue_records = {}
        # CNAME 记录：域名 -> CNAME 目标
        self.cname_records = {}
        # 最终 A 记录：域名 -> [ip列表]
        self.a_records = {}
        # 父域关系：域名或 zone -> 父域（例如："com" 的父域为根 "."；"jd.com" 的父域为 "com"）
        self.parent = {}
        # 记录每一次 DNS 查询步骤（用于生成 dns_records 表）
        self.dns_records_list = []
        # 步骤计数器
        self.step_counter = 1
        # 查询开始时间
        self.query_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        # 查询结束时间
        self.query_end_time = None
    
    def record_step(self, query_domain, parent_domain, record_type, record_values, server_used, note, status="SUCCESS"):
        """记录一次查询步骤，保存到 dns_records_list 中"""
        step = {
            "id": self.step_counter,
            "query_id": 1,  # 假设一个查询对应一个 query_id=1
            "step_number": self.step_counter,
            "query_domain": query_domain,
            "parent_domain": parent_domain,
            "record_type": record_type,
            "record_values": record_values,
            "server_used": server_used,
            "note": note,
            "status": status
        }
        self.dns_records_list.append(step)
        self.step_counter += 1

def setup_logger(domain_name):
    """设置日志记录器"""
    # 创建logs目录（如果不存在）
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 日志文件名：域名+log
    log_file = os.path.join(log_dir, f"{domain_name}_log.txt")
    
    # 配置日志记录器
    logger = logging.getLogger("dns_query")
    logger.setLevel(logging.INFO)
    
    # 清除之前的处理器（如果有）
    if logger.handlers:
        logger.handlers.clear()
    
    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 设置日志格式
    formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器到日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

class LoggingDNSResolver:
    """DNS解析器，带日志记录功能"""
    
    def __init__(self, logger):
        self.db = DNSDatabase()
        self.logger = logger
        self.resolution_status = "SUCCESS"
        self.resolution_notes = ""
    
    def send_dns_query(self, domain, rtype, ns_ip):
        """非递归 DNS 查询：构造 DNS 消息，关闭递归（RD 标志），直接发送 UDP 查询"""
        query = dns.message.make_query(domain, rtype, use_edns=True)
        query.flags &= ~dns.flags.RD  # 关闭递归查询
        start_time = time.time()
        try:
            response = dns.query.udp(query, ns_ip, timeout=5)
            query_time = (time.time() - start_time) * 1000  # 转换为毫秒
            return response, query_time
        except Exception as e:
            self.logger.info(f"  [错误] 查询 {domain} {rtype} 记录到 {ns_ip} 时出错: {e}")
            return None, 0
    
    def get_ip_for_ns(self, ns):
        """从 glue 数据库或直接查询获得 NS 主机名对应的 IP 地址"""
        if ns in self.db.glue_records and 'A' in self.db.glue_records[ns] and self.db.glue_records[ns]['A']:
            return self.db.glue_records[ns]['A'][0]
        try:
            answer = dns.resolver.resolve(ns, 'A')
            ip_list = [r.address for r in answer]
            if ns not in self.db.glue_records:
                self.db.glue_records[ns] = {}
            self.db.glue_records[ns]['A'] = ip_list
            return ip_list[0]
        except Exception as e:
            self.logger.info(f"  [错误] 解析 NS {ns} 的 IP 失败: {e}")
            return None
    
    def find_closest_parent(self, domain):
        """根据已有数据查找某域名"最近父域"的 NS 记录（查找顺序：全域 → 去掉最左标签 → … → 根）"""
        labels = domain.split('.')
        for i in range(len(labels)):
            subdomain = '.'.join(labels[i:])  # 如： "www.jd.com" 依次尝试 "www.jd.com", "jd.com", "com"
            if subdomain in self.db.ns_records:
                return subdomain, self.db.ns_records[subdomain]
        if '.' in self.db.ns_records:
            return '.', self.db.ns_records['.']
        return None, None
    
    def process_additional_section(self, response):
        """处理响应中附加部分，存储 glue 记录（A 和 AAAA）"""
        for rrset in response.additional:
            ns_name = rrset.name.to_text().rstrip('.')
            if rrset.rdtype == dns.rdatatype.A:
                a_list = [r.address for r in rrset]
                if ns_name not in self.db.glue_records:
                    self.db.glue_records[ns_name] = {}
                self.db.glue_records[ns_name]['A'] = a_list
            elif rrset.rdtype == dns.rdatatype.AAAA:
                aaaa_list = [r.address for r in rrset]
                if ns_name not in self.db.glue_records:
                    self.db.glue_records[ns_name] = {}
                self.db.glue_records[ns_name]['AAAA'] = aaaa_list
    
    def domain_dependency_resolution(self, domain, current_parent='.'):
        """依赖式分层解析函数：模拟流程，根据查询结果判断是直接得到答案还是 NS 委派，并记录每一步"""
        # 修改输出格式，使层次关系更清晰
        log_message = f"\n[解析步骤 {self.db.step_counter}]"
        log_message += f"\n  域名: {domain}"
        log_message += f"\n  父域: {'.'.join(domain.split('.')[1:]) or '.'}"  # 获取当前域名的直接父域
        
        # 查找当前域的最近父域的 NS 记录
        closest_zone, ns_list = self.find_closest_parent(domain)
        if closest_zone is None:
            closest_zone = '.'
            ns_list = self.db.ns_records.get('.', ['a.root-servers.net'])
        log_message += f"\n  最近已解析父域: {closest_zone}"
        
        if len(ns_list) > 3:
            log_message += f"\n  \"{closest_zone}\"的 NS 记录: {', '.join(ns_list[:3])}..."
        else:
            log_message += f"\n  \"{closest_zone}\"的 NS 记录: {', '.join(ns_list)}"
        
        # 从最近父域的 NS 列表中选择一个 NS
        ns = ns_list[0]
        ns_ip = self.get_ip_for_ns(ns)
        if not ns_ip:
            error_msg = f"无法获取 NS {ns} 的 IP，解析 {domain} 终止"
            log_message += f"\n  [终止] {error_msg}"
            self.logger.info(log_message)
            self.db.record_step(domain, current_parent, "ERROR", [], "", error_msg, "FAILED")
            self.resolution_status = "FAILED"
            self.resolution_notes = error_msg
            return
        
        # 确定实际查询的域名
        labels = domain.split('.')
        if closest_zone == '.':
            # 从根开始查询，只查询顶级域
            query_domain = labels[-1]  # 如 "com"
            log_message += f"\n  使用 \"{closest_zone}\"的 NS: {ns} ({ns_ip}) 查询: {query_domain}"
        else:
            # 从当前已知的最近父域开始，查询下一级域名
            # 找到最近父域在完整域名中的位置
            parent_labels = closest_zone.split('.')
            parent_len = len(parent_labels)
            if parent_labels[0] == '':  # 处理根域的特殊情况
                parent_len = 0
            # 获取下一级域名
            next_level = '.'.join(labels[-(parent_len + 1):])  # 如 "baidu.com"
            query_domain = next_level
            log_message += f"\n  使用 \"{closest_zone}\"的 NS: {ns} ({ns_ip}) 查询: {query_domain}"
        
        # 发送 DNS A 记录查询
        response, query_time = self.send_dns_query(query_domain, 'A', ns_ip)
        if response is None:
            error_msg = f"{domain} 未收到 {ns_ip} 的响应"
            log_message += f"\n  [终止] {error_msg}"
            self.logger.info(log_message)
            self.db.record_step(domain, current_parent, "ERROR", [], f"{ns} ({ns_ip})", error_msg, "FAILED")
            self.resolution_status = "FAILED"
            self.resolution_notes = error_msg
            return
        log_message += f"\n  查询耗时: {query_time:.2f}ms"
        
        # 输出日志
        self.logger.info(log_message)
        
        # 处理附加部分，存储 glue 记录
        self.process_additional_section(response)
        
        # 如果 answer 部分有记录，则根据记录类型处理
        if response.answer:
            for rrset in response.answer:
                if rrset.rdtype == dns.rdatatype.CNAME:
                    cname_target = rrset[0].target.to_text().rstrip('.')
                    self.db.record_step(domain, current_parent, "CNAME", cname_target, f"{ns} ({ns_ip})", 
                                       f"发现 CNAME 记录，指向 {cname_target}")
                    self.db.cname_records[domain] = cname_target
                    self.db.parent[domain] = current_parent
                    self.logger.info(f"  [CNAME] {domain} → {cname_target}")
                    # 递归解析 CNAME 指向的域名
                    self.domain_dependency_resolution(cname_target, current_parent=current_parent)
                    return
                elif rrset.rdtype == dns.rdatatype.A:
                    a_list = [r.address for r in rrset]
                    self.db.record_step(domain, current_parent, "A", a_list, f"{ns} ({ns_ip})", 
                                       f"成功解析 A 记录: {', '.join(a_list)}")
                    self.db.a_records[domain] = a_list
                    self.db.parent[domain] = current_parent
                    self.logger.info(f"  [解析成功] {domain} A 记录: {', '.join(a_list)}")
                    return
        
        # 如果 answer 部分没有记录，则查看 authority 部分中的 NS 委派记录
        ns_zone = None
        ns_records = []
        for rrset in response.authority:
            if rrset.rdtype == dns.rdatatype.NS:
                ns_zone = rrset.name.to_text().rstrip('.')
                ns_records = [r.target.to_text().rstrip('.') for r in rrset]
                break
        if ns_zone and ns_records:
            self.db.record_step(domain, current_parent, "NS", ns_records, f"{ns} ({ns_ip})", 
                               f"发现 {ns_zone} 的 NS 委派记录")
            if len(ns_records) > 3:
                self.logger.info(f"  [委派] 获得 {ns_zone} 的 NS 记录: {', '.join(ns_records[:3])}...")
            else:
                self.logger.info(f"  [委派] 获得 {ns_zone} 的 NS 记录: {', '.join(ns_records)}")
            # 更新 NS 记录和父域关系
            self.db.ns_records[ns_zone] = ns_records
            self.db.parent[ns_zone] = current_parent
            # 以新的最近父域重新解析同一域名
            self.domain_dependency_resolution(domain, current_parent=ns_zone)
        else:
            # 修改：如果当前查询失败，尝试直接查询完整域名
            # 记录当前查询失败
            error_msg = f"{query_domain} 未获得答案，也没有 NS 委派记录，主机不存在。"
            self.logger.info(f"  [失败] {error_msg}")
            
            """
            这个修改主要增加了以下功能：
                1. 当查询某个中间域名失败时（如 com.gslb.qianxun.com ），不会立即终止解析
                2. 而是继续尝试查询更具体的子域名（如 jd.com.gslb.qianxun.com ）
                3. 直到查询到完整域名（如 www.jd.com.gslb.qianxun.com ）
                4. 如果在这个过程中发现了 CNAME 或 A 记录，则继续正常解析流程
                5. 只有当所有尝试都失败时，才会标记为解析失败
                这样修改后，对于像 www.jd.com 这样的域名，即使中间域名不存在，也能正确解析到最终的 IP 地址。
            """

            # 如果当前查询的不是完整域名，尝试查询更具体的子域
            if query_domain != domain:
                # 尝试查询更具体的子域名，直到完整域名
                remaining_labels = domain.split('.')
                current_query = query_domain
                
                # 从当前查询域名开始，逐步添加标签，直到完整域名
                while current_query != domain:
                    # 找到下一级域名
                    next_label_index = len(domain.split('.')) - len(current_query.split('.')) - 1
                    if next_label_index < 0:
                        break
                    
                    # 构建下一级查询域名
                    next_query = '.'.join(remaining_labels[next_label_index:])
                    
                    self.logger.info(f"  使用 \"{closest_zone}\"的 NS: {ns} ({ns_ip}) 查询: {next_query}")
                    
                    # 查询下一级域名
                    next_response, next_query_time = self.send_dns_query(next_query, 'A', ns_ip)
                    self.logger.info(f"  查询耗时: {next_query_time:.2f}ms")
                    
                    if next_response is None:
                        self.logger.info(f"  [失败] {next_query} 未收到 {ns_ip} 的响应")
                        break
                    
                    # 处理附加部分
                    self.process_additional_section(next_response)
                    
                    # 检查是否有 CNAME 或 A 记录
                    if next_response.answer:
                        for rrset in next_response.answer:
                            if rrset.rdtype == dns.rdatatype.CNAME:
                                cname_target = rrset[0].target.to_text().rstrip('.')
                                self.db.record_step(next_query, current_parent, "CNAME", cname_target, 
                                                  f"{ns} ({ns_ip})", f"发现 CNAME 记录，指向 {cname_target}")
                                self.db.cname_records[next_query] = cname_target
                                self.db.parent[next_query] = current_parent
                                self.logger.info(f"  [CNAME] {next_query}->{cname_target}")
                                # 递归解析 CNAME 指向的域名
                                self.domain_dependency_resolution(cname_target, current_parent=current_parent)
                                return
                            elif rrset.rdtype == dns.rdatatype.A:
                                a_list = [r.address for r in rrset]
                                self.db.record_step(next_query, current_parent, "A", a_list, 
                                                  f"{ns} ({ns_ip})", f"成功解析 A 记录: {', '.join(a_list)}")
                                self.db.a_records[next_query] = a_list
                                self.db.parent[next_query] = current_parent
                                self.logger.info(f"  [解析成功] {next_query} A 记录: {', '.join(a_list)}")
                                return
                    
                    # 如果没有找到记录，继续尝试下一级
                    self.logger.info(f"  [失败] {next_query} 未获得答案，也没有 NS 委派记录，主机不存在。")
                    current_query = next_query
                    
                    # 如果已经查询到完整域名，则终止
                    if current_query == domain:
                        break
            
            # 如果所有尝试都失败，记录最终失败状态
            self.db.record_step(domain, current_parent, "ERROR", [], f"{ns} ({ns_ip})", 
                               f"{domain} 未获得答案，也没有 NS 委派记录", "FAILED")
            self.resolution_status = "FAILED"
            self.resolution_notes = f"{domain} 未获得答案，也没有 NS 委派记录"
    def output_result(self, original_domain):
        """输出解析结果，包括查询记录、DNS记录、glue记录和域名依赖关系"""
        self.db.query_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # 构造查询记录表
        queries = [{
            "id": 1,
            "domain_name": original_domain,
            "resolution_status": self.resolution_status,
            "notes": self.resolution_notes if self.resolution_status == "FAILED" else f"{original_domain} 解析成功",
            "start_time": self.db.query_start_time,
            "end_time": self.db.query_end_time,
            "total_steps": self.db.step_counter - 1
        }]
        
        # 将 glue_records 从字典转换为列表，id 自增
        glue_list = []
        glue_id = 1
        for ns_name, rec in self.db.glue_records.items():
            a_records = rec.get("A", [])
            aaaa_records = rec.get("AAAA", [])
            
            # 分别为每个 IP 地址创建一条记录，提高规范化
            for a_record in a_records:
                glue_list.append({
                    "id": glue_id,
                    "ns_name": ns_name,
                    "record_type": "A",
                    "ip_address": a_record
                })
                glue_id += 1
                
            for aaaa_record in aaaa_records:
                glue_list.append({
                    "id": glue_id,
                    "ns_name": ns_name,
                    "record_type": "AAAA",
                    "ip_address": aaaa_record
                })
                glue_id += 1
        
        # 构建域名依赖关系表
        dependencies = []
        dep_id = 1
        for domain, parent in self.db.parent.items():
            if parent is not None:  # 排除根域
                dependencies.append({
                    "id": dep_id,
                    "domain": domain,
                    "parent_domain": parent
                })
                dep_id += 1
        
        # 最终结果
        result = {
            "queries": queries,
            "dns_records": self.db.dns_records_list,
            "glue_records": glue_list,
            "domain_dependencies": dependencies
        }
        
        self.logger.info("\n================ 最终解析结果（数据库格式） ================")
        import json
        self.logger.info(json.dumps(result, ensure_ascii=False, indent=4))
        
        # 输出解析路径摘要
        self.logger.info("\n================ 解析路径摘要 ================")
        for i, step in enumerate(self.db.dns_records_list, 1):
            record_values = step["record_values"]
            if isinstance(record_values, list):
                if len(record_values) > 3:
                    values_str = f"{', '.join(str(v) for v in record_values[:3])}... (共{len(record_values)}条)"
                else:
                    values_str = ', '.join(str(v) for v in record_values)
            else:
                values_str = str(record_values)
                
            self.logger.info(f"步骤 {i}: [{step['record_type']}] {step['query_domain']} → {values_str}")
            self.logger.info(f"    服务器: {step['server_used']}")
            self.logger.info(f"    说明: {step['note']}")

def main():
    """主函数：设置日志记录器，实例化LoggingDNSResolver，启动域名解析并输出结果"""
    if len(sys.argv) > 1:
        domain = sys.argv[1]
    else:
        domain = "www.jd.com"  # 默认域名
    
    # 设置日志记录器
    logger = setup_logger(domain)
    
    # 记录开始信息
    logger.info(f"开始解析 {domain} 的依赖关系路径 ...")
    logger.info(f"日志时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # 实例化解析器并开始解析
    resolver = LoggingDNSResolver(logger)
    resolver.domain_dependency_resolution(domain, current_parent='.')
    resolver.output_result(domain)
    
    # 记录结束信息
    logger.info("=" * 60)
    log_path = os.path.join("logs", f"{domain}_log.txt")
    logger.info(f"解析完成，日志已保存至: {log_path}")

if __name__ == "__main__":
    main()