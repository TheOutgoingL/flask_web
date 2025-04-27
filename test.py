# -*- coding: utf-8 -*-
# @Time    : 2024/5/31 下午8:48
# @Author  : lyx
# @File    : test.py

from flask import Flask, request, jsonify, render_template
import socket
import requests
import dns.resolver
from flask_sqlalchemy import SQLAlchemy
import json
from urllib.parse import quote_plus


def get_familyDomain(domain):
    segments = domain.split(".")
    family_domain = []
    #  输出segments列表的大小
    print(len(segments))
    for i in range(len(segments), 1, -1):
        try_domain = ".".join(segments[len(segments) - i:])
        # print(try_domain)
        family_domain.append(try_domain)
    # 去除第一个元素
    # family_domain = family_domain[0:]
    print(family_domain)
    return  family_domain
# get_familyDomain(domain)

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
    # print(ips_info)

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
    family_domains_set = set()
    auth_dns_list = []
    auth_ip_list = []
    dns_ip_set = set()
    find_by_dns_set = set()
    ips_info_list = []

    for record in domain_info:
        dns_set.add(record[0])
        cname_set.add(record[1])
        family_domains_set.update(record[2])

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
        'Family_Domains': list(family_domains_set),
        'Auth_DNS': auth_dns_list,
        'Auth_IP': auth_ip_list,
        'DNS_IP': list(dns_ip_set),
        'FindBy_DNS': list(find_by_dns_set),
        'IP_Info': ips_info_list  # 包含所有IP和NS IP的国家和ISP信息
    }
    return domain_info_dict

def get_all_ips(domain):
    try:
        answers = dns.resolver.resolve(domain, 'A')
        ips = [str(rdata) for rdata in answers]
        return ips
    except dns.resolver.NoAnswer:
        print(f"无法找到域名 {domain} 的IP地址")
        return []

def get_ip_info(ip):
    try:
        # print(ip)
        response = requests.get(f"https://api.vvhan.com/api/ipInfo?ip={ip}")
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                info = data.get("info", {})
                return {
                    "ip": data.get("ip"),
                    "country": info.get("country", "未知"),
                    "isp": info.get("isp", "未知")
                }
            else:
                print(f"未能成功获取IP信息: {data}")
                return {"ip": ip, "country": "未知", "isp": "未知"}
        else:
            print(f"获取IP信息失败，状态码: {response.status_code}")
            return {"ip": ip, "country": "未知", "isp": "未知"}
    except requests.RequestException as e:
        print(f"请求过程中出现错误: {e}")
        return {"ip": ip, "country": "未知", "isp": "未知"}
# print(clean_data(get_domainInfo(domain)))

def get_ips_info(domain):
    ips = get_all_ips(domain)
    ip_info_list = []
    for ip in ips:
        info = get_ip_info(ip)
        ip_info_list.append(info)
    return ip_info_list

domain = ("www.tjut.edu.cn")
# ip_info = get_ip_info("110.242.68.3")
# print(ip_info)

print((get_domainInfo(domain)))
print(clean_data(get_domainInfo(domain)))
print(get_all_ips(domain))