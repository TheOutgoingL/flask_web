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
from collections import defaultdict

class DNSDatabase:
    """数据库结构：存放各级 NS、glue、CNAME、A 记录以及父域关系和查询过程记录"""
    def __init__(self):
        self.ns_records = {}
        self.glue_records = {}
        self.cname_records = {}
        self.a_records = {}
        self.parent = {}
        self.dns_records_list = []
        self.step_counter = 1
        self.query_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.query_end_time = None
        self.failed_queries = []
        self.resolution_path = []
    
    def record_step(self, query_domain, parent_domain, record_type, record_values, server_used, note, status="SUCCESS", query_time=0, failed_attempts=None):
        """记录一次查询步骤"""
        step = {
            "id": self.step_counter,
            "step_number": self.step_counter,
            "query_domain": query_domain,
            "parent_domain": parent_domain,
            "record_type": record_type,
            "record_values": record_values,
            "server_used": server_used,
            "note": note,
            "status": status,
            "query_time": query_time
        }
        if failed_attempts:
            step["failed_attempts"] = failed_attempts
        self.dns_records_list.append(step)
        self.step_counter += 1

        # 记录解析路径
        if record_type == "CNAME":
            self.resolution_path.append(f"{query_domain} → CNAME → {record_values}")
        elif record_type == "A":
            self.resolution_path.append(f"{query_domain} → A → {record_values[0]}")
    
    def add_failed_query(self, query, error):
        """记录失败的查询尝试"""
        self.failed_queries.append({
            "query": query,
            "error": error
        })

def setup_logger(domain_name):
    """设置日志记录器"""
    log_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{domain_name}_log.json")
    
    logger = logging.getLogger("dns_query")
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        logger.handlers.clear()
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger

class LoggingDNSResolver:
    """DNS解析器，带日志记录功能"""
    
    def __init__(self, logger):
        self.db = DNSDatabase()
        self.logger = logger
        self.resolution_status = "SUCCESS"
        self.resolution_notes = ""
        self.original_domain = ""
    
    def send_dns_query(self, domain, rtype, ns_ip):
        """非递归 DNS 查询"""
        query = dns.message.make_query(domain, rtype, use_edns=True)
        query.flags &= ~dns.flags.RD
        start_time = time.time()
        try:
            response = dns.query.udp(query, ns_ip, timeout=5)
            query_time = (time.time() - start_time) * 1000
            return response, query_time
        except Exception as e:
            self.db.add_failed_query(domain, str(e))
            return None, 0
    
    def get_ip_for_ns(self, ns):
        """获取NS服务器IP"""
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
            self.db.add_failed_query(ns, str(e))
            return None
    
    def find_closest_parent(self, domain):
        """查找最近父域"""
        labels = domain.split('.')
        for i in range(len(labels)):
            subdomain = '.'.join(labels[i:])
            if subdomain in self.db.ns_records:
                return subdomain, self.db.ns_records[subdomain]
        if '.' in self.db.ns_records:
            return '.', self.db.ns_records['.']
        return None, None
    
    def process_additional_section(self, response):
        """处理附加记录"""
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
    
    def domain_dependency_resolution(self, domain, current_parent='.', is_cname_followup=False):
        """分层解析函数，支持CNAME递归解析"""
        # 如果是CNAME跟进，重置父域为根
        if is_cname_followup:
            current_parent = '.'
        
        closest_zone, ns_list = self.find_closest_parent(domain)
        if closest_zone is None:
            closest_zone = '.'
            ns_list = self.db.ns_records.get('.', ['a.root-servers.net'])
        
        # 获取NS服务器IP
        ns = ns_list[0]
        ns_ip = self.get_ip_for_ns(ns)
        if not ns_ip:
            self.resolution_status = "FAILED"
            self.resolution_notes = f"无法获取NS {ns}的IP"
            self.db.record_step(domain, current_parent, "ERROR", [], "", self.resolution_notes, "FAILED")
            return None
        
        # 确定查询类型：如果是CNAME跟进或者是顶级查询，先查NS
        query_type = 'NS' if closest_zone == domain else 'A'
        
        # 发送查询
        response, query_time = self.send_dns_query(domain, query_type, ns_ip)
        if response is None:
            self.resolution_status = "FAILED"
            self.resolution_notes = f"{domain}未收到响应"
            self.db.record_step(domain, current_parent, "ERROR", [], f"{ns} ({ns_ip})", 
                            self.resolution_notes, "FAILED", query_time)
            return None
        
        self.process_additional_section(response)
        
        # 处理CNAME记录
        if response.answer:
            for rrset in response.answer:
                if rrset.rdtype == dns.rdatatype.CNAME:
                    cname_target = rrset[0].target.to_text().rstrip('.')
                    self.db.record_step(
                        domain, current_parent, "CNAME", cname_target,
                        f"{ns} ({ns_ip})", f"发现CNAME记录: {cname_target}",
                        "SUCCESS", query_time
                    )
                    self.db.cname_records[domain] = cname_target
                    # 递归解析CNAME目标
                    return self.domain_dependency_resolution(cname_target, is_cname_followup=True)
        
        # 处理A记录
        if response.answer:
            for rrset in response.answer:
                if rrset.rdtype == dns.rdatatype.A:
                    a_list = [r.address for r in rrset]
                    self.db.record_step(
                        domain, current_parent, "A", a_list,
                        f"{ns} ({ns_ip})", f"成功解析A记录: {', '.join(a_list)}",
                        "SUCCESS", query_time
                    )
                    self.db.a_records[domain] = a_list
                    return a_list
        
        # 处理NS委派
        ns_zone = None
        ns_records = []
        for rrset in response.authority:
            if rrset.rdtype == dns.rdatatype.NS:
                ns_zone = rrset.name.to_text().rstrip('.')
                ns_records = [r.target.to_text().rstrip('.') for r in rrset]
                break
        
        if ns_zone and ns_records:
            self.db.record_step(
                ns_zone, current_parent, "NS", ns_records,
                f"{ns} ({ns_ip})", f"发现{ns_zone}的NS委派记录",
                "DELEGATION", query_time
            )
            self.db.ns_records[ns_zone] = ns_records
            self.db.parent[ns_zone] = current_parent
            return self.domain_dependency_resolution(domain, current_parent=ns_zone)
        
        # 如果没有得到任何有效记录
        self.resolution_status = "FAILED"
        self.resolution_notes = f"{domain}未获得答案"
        self.db.record_step(
            domain, current_parent, "ERROR", [],
            f"{ns} ({ns_ip})", self.resolution_notes,
            "FAILED", query_time
        )
        return None
    
    # def domain_dependency_resolution(self, domain, current_parent='.'):
    #     """分层解析函数"""
    #     closest_zone, ns_list = self.find_closest_parent(domain)
    #     if closest_zone is None:
    #         closest_zone = '.'
    #         ns_list = self.db.ns_records.get('.', ['a.root-servers.net'])
        
    #     ns = ns_list[0]
    #     ns_ip = self.get_ip_for_ns(ns)
    #     if not ns_ip:
    #         self.resolution_status = "FAILED"
    #         self.resolution_notes = f"无法获取NS {ns}的IP"
    #         self.db.record_step(closest_zone, current_parent, "ERROR", [], "", self.resolution_notes, "FAILED")
    #         return
        
    #     # 确定实际查询的域名
    #     if closest_zone == '.':
    #         query_domain = 'com.'  # 根查询总是查询TLD
    #     else:
    #         query_domain = closest_zone
        
    #     response, query_time = self.send_dns_query(query_domain, 'NS', ns_ip)
        
    #     labels = domain.split('.')
    #     if closest_zone == '.':
    #         query_domain = labels[-1]
    #     else:
    #         parent_labels = closest_zone.split('.')
    #         parent_len = len(parent_labels)
    #         if parent_labels[0] == '':
    #             parent_len = 0
    #         query_domain = '.'.join(labels[-(parent_len + 1):])
        
    #     response, query_time = self.send_dns_query(query_domain, 'A', ns_ip)
    #     if response is None:
    #         self.resolution_status = "FAILED"
    #         self.resolution_notes = f"{domain}未收到响应"
    #         self.db.record_step(domain, current_parent, "ERROR", [], f"{ns} ({ns_ip})", self.resolution_notes, "FAILED", query_time)
    #         return
        
    #     self.process_additional_section(response)
        
    #     if response.answer:
    #         for rrset in response.answer:
    #             if rrset.rdtype == dns.rdatatype.CNAME:
    #                 cname_target = rrset[0].target.to_text().rstrip('.')
    #                 # 处理CNAME记录时
    #                 self.db.record_step(
    #                     domain,  # 实际查询的域名
    #                     current_parent,
    #                     "CNAME", 
    #                     cname_target,
    #                     f"{ns} ({ns_ip})",
    #                     f"发现CNAME记录: {cname_target}",
    #                     "SUCCESS",
    #                     query_time
    #                 )
    #                 self.db.cname_records[domain] = cname_target
    #                 self.db.parent[domain] = current_parent
    #                 self.domain_dependency_resolution(cname_target, current_parent)
    #                 return
                
    #             elif rrset.rdtype == dns.rdatatype.A:
    #                 a_list = [r.address for r in rrset]
    #                 # 处理A记录时
    #                 self.db.record_step(
    #                     domain,  # 实际查询的域名
    #                     current_parent,
    #                     "A",
    #                     a_list,
    #                     f"{ns} ({ns_ip})",
    #                     f"成功解析A记录: {', '.join(a_list)}",
    #                     "SUCCESS",
    #                     query_time
    #                 )       
    #                 self.db.a_records[domain] = a_list
    #                 self.db.parent[domain] = current_parent
    #                 return
        
    #     # 处理NS委派
    #     ns_zone = None
    #     ns_records = []
    #     for rrset in response.authority:
    #         if rrset.rdtype == dns.rdatatype.NS:
    #             ns_zone = rrset.name.to_text().rstrip('.')
    #             ns_records = [r.target.to_text().rstrip('.') for r in rrset]
    #             break
        
    #     if ns_zone and ns_records:
    #         # 在处理NS记录时
    #         self.db.record_step(
    #             ns_zone,  # 记录实际查询的域
    #             current_parent, 
    #             "NS", 
    #             ns_records,
    #             f"{ns} ({ns_ip})", 
    #             f"发现{ns_zone}的NS委派记录", 
    #             "DELEGATION", 
    #             query_time
    #         )
    #         self.db.ns_records[ns_zone] = ns_records
    #         self.db.parent[ns_zone] = current_parent
    #         self.domain_dependency_resolution(domain, current_parent=ns_zone)
    #     else:
    #         self.resolution_status = "FAILED"
    #         self.resolution_notes = f"{query_domain}未获得答案"
    #         failed_attempts = []
    #         if query_domain != domain:
    #             remaining_labels = domain.split('.')
    #             current_query = query_domain
    #             while current_query != domain:
    #                 next_label_index = len(domain.split('.')) - len(current_query.split('.')) - 1
    #                 if next_label_index < 0:
    #                     break
    #                 next_query = '.'.join(remaining_labels[next_label_index:])
    #                 next_response, next_query_time = self.send_dns_query(next_query, 'A', ns_ip)
    #                 if next_response is None:
    #                     failed_attempts.append({
    #                         "query": next_query,
    #                         "error": "无响应"
    #                     })
    #                     break
    #                 self.process_additional_section(next_response)
    #                 current_query = next_query
            
    #         self.db.record_step(
    #             domain, current_parent, "ERROR", [], 
    #             f"{ns} ({ns_ip})", self.resolution_notes, 
    #             "FAILED", query_time, failed_attempts
    #         )
    
    def _calculate_total_time(self):
        """计算总耗时"""
        fmt = "%Y-%m-%d %H:%M:%S.%f"
        start = datetime.strptime(self.db.query_start_time, fmt)
        end = datetime.strptime(self.db.query_end_time, fmt)
        return f"{(end - start).total_seconds() * 1000:.2f}ms"
    
    def _build_resolution_path(self):
        """构建解析路径，正确处理CNAME链"""
        path = []
        current = self.original_domain
        visited = set()
        
        while current in self.db.cname_records and current not in visited:
            visited.add(current)
            target = self.db.cname_records[current]
            path.append(f"{current} → CNAME → {target}")
            current = target
        
        if current in self.db.a_records:
            path.append(f"{current} → A → {self.db.a_records[current][0]}")
        
        return path
    
    def _format_glue_records(self):
        """格式化Glue记录"""
        return {
            ns: {
                "A": data.get("A", []),
                "AAAA": data.get("AAAA", [])
            }
            for ns, data in self.db.glue_records.items()
        }
    
    def _build_domain_dependencies(self):
        """构建域名依赖关系"""
        dependencies = defaultdict(list)
        for domain, parent in self.db.parent.items():
            if parent != "null":
                dependencies[parent].append(domain)
        return dict(dependencies)
    
    def output_result(self, original_domain):
        """输出最终结果"""
        self.db.query_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.original_domain = original_domain
        
        result = {
            original_domain: {
                "解析步骤": [],
                "解析总结": {
                    "总耗时": self._calculate_total_time(),
                    "跳转路径": self._build_resolution_path(),
                    "最终IP": self.db.a_records.get(self._get_final_domain(), [""])[0],
                    "解析状态": self.resolution_status,
                    "开始时间": self.db.query_start_time,
                    "结束时间": self.db.query_end_time,
                    "备注": self.resolution_notes
                },
                "Glue记录": self._format_glue_records(),
                "域名依赖关系": self._build_domain_dependencies()
            }
        }
        
        for step in self.db.dns_records_list:
            formatted_step = {
                "步骤": step["step_number"],
                "查询内容": step["query_domain"],  # 现在只保留这一个字段
                "父域": step["parent_domain"],
                "最近已解析父域": self._get_recent_parent(step),
                "使用的NS服务器": step["server_used"],
                "查询耗时": f"{step['query_time']:.2f}ms",
                "结果": self._format_step_result(step),
                "状态": step["status"],
                "备注": step["note"]
            }
            if "failed_attempts" in step:
                formatted_step["失败查询"] = step["failed_attempts"]
            result[original_domain]["解析步骤"].append(formatted_step)
    
        self.logger.info(json.dumps(result, ensure_ascii=False, indent=4))
    
    def _get_recent_parent(self, step):
        """获取最近已解析父域"""
        return step["parent_domain"] if step["parent_domain"] != "null" else "."
    
    # def _get_query_content(self, step):
    #     """获取查询内容"""
    #     if step["record_type"] == "CNAME":
    #         return step["query_domain"]
    #     elif step["record_type"] == "NS":
    #         # 对于NS查询，显示正在查询的完整域名
    #         return step["query_domain"]
    #     elif step["record_type"] == "A":
    #         # 对于A记录查询，显示完整的查询域名
    #         return step["query_domain"]
    #     return step["query_domain"]
    
    def _format_step_result(self, step):
        """格式化步骤结果"""
        if step["record_type"] in ["ERROR", "DELEGATION"]:
            return {"类型": step["record_type"]}
        
        return {
            "类型": step["record_type"],
            "记录": step["record_values"] if isinstance(step["record_values"], list) else [step["record_values"]]
        }
    
    def _get_final_domain(self):
        """获取最终解析域名"""
        current = self.original_domain
        while current in self.db.cname_records:
            current = self.db.cname_records[current]
        return current

def main():
    if len(sys.argv) < 2:
        print("Usage: python dns_query_log.py <domain>")
        sys.exit(1)
    
    domain_name = sys.argv[1]
    logger = setup_logger(domain_name)
    
    resolver = LoggingDNSResolver(logger)
    resolver.db.ns_records['.'] = ['a.root-servers.net']
    
    resolver.domain_dependency_resolution(domain_name)
    resolver.output_result(domain_name)

if __name__ == "__main__":
    main()