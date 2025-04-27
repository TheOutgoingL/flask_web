let isAggregate = false; // 初始化模式为分离态

// 页面加载完成后自动执行查询（如果有域名参数）
document.addEventListener('DOMContentLoaded', function() {
    const domainInput = document.getElementById('domain');
    if (domainInput.value.trim() !== '') {
        queryDomain();
    }
    
    // 获取服务器计数
    fetchServerCount();
});

function queryDomain() {
    const domain = document.getElementById('domain').value;
    const loadingBar = document.getElementById('loading-bar');
    const recordsDiv = document.getElementById('records');

    // 显示加载条并启动动画
    loadingBar.style.width = '50%';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/query', true);
    xhr.setRequestHeader('Content-Type', 'application/json;charset=UTF-8');
    xhr.onreadystatechange = function () {
        if (xhr.readyState === 4) {
            // 将加载条宽度设置为100%，然后隐藏加载条
            loadingBar.style.width = '100%';
            setTimeout(() => {
                loadingBar.style.width = '0';
            }, 500);

            if (xhr.status === 200) {
                const data = JSON.parse(xhr.responseText);
                const nodes = []; // 存储节点
                const edges = []; // 存储边
                const nodeIds = new Set(); // 存储已有节点的ID

                // 添加查询记录
                const newRecord = document.createElement('div');
                newRecord.textContent = domain;
                recordsDiv.appendChild(newRecord);

                // 添加节点和边的函数，避免重复
                const addNodesAndEdges = (domainData) => {
                    // 辅助函数检查边是否已存在
                    const edgeExists = (from, to, label) => {
                        return edges.some(edge => edge.from === from && edge.to === to && edge.label === label);
                    };

                    const findByDNSNodes = (domainData.FindBy_DNS || []).map((dns, i) => ({
                        id: `find_by_dns_${dns}`,
                        label: dns,
                        group: 'find_by_dns'
                    }));
                    // CNAME存在才创建

                    const dnsNodes = (domainData.DNS || []).map((dns, i) => ({
                        id: `${dns}`,
                        label: dns,
                        group: 'dns'
                    }));
                    dnsNodes.forEach(node => {
                        if (!nodeIds.has(node.id)) {
                            nodes.push(node);
                            nodeIds.add(node.id);
                        }
                    });

                    const authIPNodes = (domainData.Auth_IP || []).map((ip) => ({
                        id: `auth_ip_${ip}`,
                        label: ip,
                        group: 'auth_ip'
                    }));
                    authIPNodes.forEach(node => {
                        if (!nodeIds.has(node.id)) {
                            nodes.push(node);
                            nodeIds.add(node.id);
                        }
                    });

                    const authDNSNodes = (domainData.Auth_DNS || []).map((dns, i) => ({
                        id: `auth_dns_${dns}`,
                        label: dns,
                        group: 'auth_dns'
                    }));
                    authDNSNodes.forEach(node => {
                        if (!nodeIds.has(node.id)) {
                            nodes.push(node);
                            nodeIds.add(node.id);
                        }
                    });

                    const familyDomainsNodes = (domainData.Family_Domains || []).map((dns, i) => ({
                        id: `${dns}`,
                        label: dns,
                        group: 'family_domains'
                    }));
                    if (familyDomainsNodes.length > 1) {  // 大于1 才需要创建这个节点  创建DNS的父域
                        familyDomainsNodes.forEach((node) => {
                            if (!nodeIds.has(node.id)) {
                                nodes.push(node);
                                nodeIds.add(node.id);
                            }
                        });
                    }


                    const cnameNodes = (domainData.CNAME || []).map((cname, i) => ({
                        id: `cname_${cname}`,
                        label: cname,
                        group: 'cname'
                    }));
                    if (cnameNodes.length > 0 && cnameNodes[0].label !== "null") {
                        cnameNodes.forEach(node => {
                            if (!nodeIds.has(node.id)) {
                                nodes.push(node);
                                nodeIds.add(node.id);
                            }
                        });

                        // 如果有cname  那就创建一个findBy的节点
                        findByDNSNodes.forEach(node => {
                            if (!nodeIds.has(node.id)) {
                                nodes.push(node);
                                nodeIds.add(node.id);
                            }
                        });
                    }


                    const dnsIPNodes = (domainData.DNS_IP || []).map((ip, i) => ({
                        id: `dns_ip_${ip}`,
                        label: ip,
                        group: 'dns_ip'
                    }));
                    dnsIPNodes.forEach(node => {
                        if (!nodeIds.has(node.id)) {
                            nodes.push(node);
                            nodeIds.add(node.id);
                        }
                    });


                    const ipCountryNodes = (domainData.IP_Info || []).map((info) => ({
                        id: `country_of_${info.ip}`,
                        label: info.country,
                        group: 'ip_country'
                    }));
                    ipCountryNodes.forEach(node => {
                        if (!nodeIds.has(node.id)) {
                            nodes.push(node);
                            nodeIds.add(node.id);
                        }
                    });
                    const ipISPNodes = (domainData.IP_Info || []).map((info) => ({
                        id: `isp_of_${info.ip}`,
                        label: info.isp,
                        group: 'ip_isp'
                    }));
                    ipISPNodes.forEach(node => {
                        if (!nodeIds.has(node.id)) {
                            nodes.push(node);
                            nodeIds.add(node.id);
                        }
                    });

                    // 连接DNSIP的国家和ISP
                    dnsIPNodes.forEach(dnsIPNode => {
                        const ip = dnsIPNode.label // 获取ip地址

                        // dns_ip ----> country
                        const countryNodeId = `country_of_${ip}`;

                        if (nodeIds.has(countryNodeId)) {
                            if (!edgeExists(dnsIPNode.id, countryNodeId, 'locatedIn')) {
                                edges.push({
                                    from: dnsIPNode.id,
                                    to: countryNodeId,
                                    label: 'locatedIn',
                                    arrows: 'to'
                                });
                            }
                        }

                        // dns_ip ----> ISP
                        const ispNodeId = `isp_of_${ip}`;
                        if (nodeIds.has(ispNodeId)) {
                            if (!edgeExists(dnsIPNode.id, ispNodeId, 'providedBy')) {
                                edges.push({
                                    from: dnsIPNode.id,
                                    to: ispNodeId,
                                    label: 'providedBy',
                                    arrows: 'to'
                                });
                            }
                        }

                    });

                    // 连接AuthIP的国家和ISP
                    authIPNodes.forEach(authIPNode => {
                        const ip = authIPNode.label;  // 获取IP地址

                        // 连接到国家节点
                        const countryNodeId = `country_of_${ip}`;
                        if (nodeIds.has(countryNodeId)) {
                            if (!edgeExists(authIPNode.id, countryNodeId, 'locatedIn')) {
                                edges.push({
                                    from: authIPNode.id,
                                    to: countryNodeId,
                                    label: 'locatedIn',
                                    arrows: 'to'
                                });
                            }
                        }


                        // 连接到ISP节点
                        const ispNodeId = `isp_of_${ip}`;
                        if (nodeIds.has(ispNodeId)) {
                            if (!edgeExists(authIPNode.id, ispNodeId, 'providedBy')) {
                                edges.push({
                                    from: authIPNode.id,
                                    to: ispNodeId,
                                    label: 'providedBy',
                                    arrows: 'to'
                                });
                            }
                        }
                    });


                    // 权威服务器和authip的边
                    authDNSNodes.forEach((authDNSNode, i) => {
                        if (authIPNodes[i]) {
                            if (!edgeExists(authDNSNode.id, authIPNodes[i].id, ' resolvesTo')) {
                                edges.push({
                                    from: authDNSNode.id,
                                    to: authIPNodes[i].id,
                                    label: ' resolvesTo',
                                    arrows: 'to'
                                });
                            }
                            if (!edgeExists(authIPNodes[i].id, authDNSNode.id, 'isResolvedBy')) {
                                edges.push({
                                    from: authIPNodes[i].id,
                                    to: authDNSNode.id,
                                    label: 'isResolvedBy',
                                    arrows: 'to'
                                });
                            }
                        }
                    });

                    //如果没有cname
                    if (cnameNodes[0].label === "null") {
                        console.log(familyDomainsNodes.length)
                        authDNSNodes.forEach((authDNSNode) => {
                            if (familyDomainsNodes.length === 1) {  // 形如 baidu.com ，那就直接从dnsNode连到NS记录
                                if (!edgeExists(dnsNodes[0].id, authDNSNode.id, 'isDelegatedTo')) {
                                    edges.push({
                                        from: dnsNodes[0].id,
                                        to: authDNSNode.id,
                                        label: 'isDelegatedTo',
                                        arrows: 'to'
                                    });
                                }
                            }

                            if (familyDomainsNodes.length > 1) {  // 形如 www.baidu.com
                                const index_family = familyDomainsNodes.findIndex(node => ('find_by_dns_' + node.id) === findByDNSNodes[0].id);
                                console.log(familyDomainsNodes[index_family].id)
                                if (!edgeExists(familyDomainsNodes[index_family].id, authDNSNode.id, 'isDelegatedTo')) {
                                    edges.push({
                                        from: familyDomainsNodes[index_family].id,
                                        to: authDNSNode.id,
                                        label: 'isDelegatedTo',
                                        arrows: 'to'
                                    });
                                }
                            }
                        });
                        dnsNodes.forEach((dnsNode) => {
                            dnsIPNodes.forEach((dnsIPNode) => {
                                // dns---dnsip
                                if (!edgeExists(dnsNode.id, dnsIPNode.id, 'resolvesTo')) {
                                    edges.push({
                                        from: dnsNode.id,
                                        to: dnsIPNode.id,
                                        label: 'resolvesTo',
                                        arrows: 'to'
                                    });
                                }
                                // dnsip---dns
                                if (!edgeExists(dnsIPNode.id, dnsNode.id, 'isResolvedBy')) {
                                    edges.push({
                                        from: dnsIPNode.id,
                                        to: dnsNode.id,
                                        label: 'isResolvedBy',
                                        arrows: 'to'
                                    });
                                }
                            });
                        });
                        if (familyDomainsNodes.length > 1) {
                            // 父域链
                            // 遍历familyDomainsNodes，添加边
                            for (let i = 0; i < familyDomainsNodes.length - 1; i++) {
                                const fromNode = familyDomainsNodes[i];
                                const toNode = familyDomainsNodes[i + 1];
                                if (!edgeExists(fromNode.id, toNode.id, 'isSubdomainOf')) {
                                    edges.push({
                                        from: fromNode.id,
                                        to: toNode.id,
                                        label: 'isSubdomainOf',
                                        arrows: 'to'
                                    });
                                }
                            }
                        }
                    }

                    // 如果有cname
                    if (cnameNodes.length > 0 && cnameNodes[0].label !== "null") {
                        // dns---cname
                        if (!edgeExists(dnsNodes[0].id, cnameNodes[0].id, 'hasAlias')) {
                            edges.push({
                                from: dnsNodes[0].id,
                                to: cnameNodes[0].id,
                                label: 'hasAlias',
                                arrows: 'to'
                            });
                        }
                        if (findByDNSNodes.length > 0) {
                            // cname---findbydns
                            if (!edgeExists(cnameNodes[0].id, findByDNSNodes[0].id, 'isSubdomainOf')) {
                                edges.push({
                                    from: cnameNodes[0].id,
                                    to: findByDNSNodes[0].id,
                                    label: 'isSubdomainOf',
                                    arrows: 'to'
                                });
                            }
                            authDNSNodes.forEach((authDNSNode, i) => {
                                // findby---ns
                                if (!edgeExists(findByDNSNodes[0].id, authDNSNode.id, 'isDelegatedTo')) {
                                    edges.push({
                                        from: findByDNSNodes[0].id,
                                        to: authDNSNode.id,
                                        label: 'isDelegatedTo',
                                        arrows: 'to'
                                    });
                                }
                            });
                            dnsNodes.forEach((dnsNode) => {
                                dnsIPNodes.forEach((dnsIPNode) => {
                                    // dns---dnsip
                                    if (!edgeExists(dnsNode.id, dnsIPNode.id, 'resolvesTo')) {
                                        edges.push({
                                            from: dnsNode.id,
                                            to: dnsIPNode.id,
                                            label: 'resolvesTo',
                                            arrows: 'to'
                                        });
                                    }
                                    // dnsip---dns
                                    if (!edgeExists(dnsIPNode.id, dnsNode.id, 'isResolvedBy')) {
                                        edges.push({
                                            from: dnsIPNode.id,
                                            to: dnsNode.id,
                                            label: 'isResolvedBy',
                                            arrows: 'to'
                                        });
                                    }
                                });
                                if (familyDomainsNodes.length > 1) {
                                    // 父域链
                                    // 遍历familyDomainsNodes，添加边
                                    for (let i = 0; i < familyDomainsNodes.length - 1; i++) {
                                        const fromNode = familyDomainsNodes[i];
                                        const toNode = familyDomainsNodes[i + 1];
                                        edges.push({
                                            from: fromNode.id,
                                            to: toNode.id,
                                            label: 'isSubdomainOf',
                                            arrows: 'to'
                                        });
                                    }
                                }
                            });
                        }
                    }
                };

                // 检查响应是单个对象还是对象列表
                if (Array.isArray(data)) {
                    data.forEach(domainData => addNodesAndEdges(domainData));
                } else {
                    addNodesAndEdges(data);
                }

                // 更新vis.js网络数据
                const container = document.getElementById("mynetwork");
                const visNodes = new vis.DataSet(nodes);
                const visEdges = new vis.DataSet(edges);
                const visData = {nodes: visNodes, edges: visEdges};
                const options = {
                    groups: {
                        auth_dns: {shape: 'box', color: {background: 'lightgreen'}},
                        auth_ip: {shape: 'box', color: {background: 'lightblue'}},
                        cname: {shape: 'box', color: {background: 'pink'}},
                        dns: {color: {background: '#B5BEED'}, font: {multi: 'md', size: 20}},
                        dns_ip: {shape: 'box', color: {background: 'yellow'}},
                        family_domains: {shape: 'box', color: {background: 'skyblue'}}
                    },
                    physics: {
                        barnesHut: {
                            springLength: 180, // 增加节点之间的距离
                        }
                    },
                    edges: {
                        smooth: true,
                        arrows: {
                            to: {
                                enabled: true,
                            }
                        }
                    },
                    interaction: {
                        zoomView: false // 禁用默认的滚轮缩放功能
                    }
                };

                const network = new vis.Network(container, visData, options);

                // 添加键盘事件监听器
                let ctrlPressed = false;
                document.addEventListener('keydown', function (event) {
                    if (event.ctrlKey) {
                        ctrlPressed = true;
                        network.setOptions({interaction: {zoomView: true}});
                    }
                });
                document.addEventListener('keyup', function (event) {
                    if (!event.ctrlKey) {
                        ctrlPressed = false;
                        network.setOptions({interaction: {zoomView: false}});
                    }
                });

                // 添加双击事件监听器
                network.on('doubleClick', function (params) {
                    if (params.nodes.length > 0) {
                        const clickedNode = visNodes.get(params.nodes[0]);
                        const groupMap = {
                            'auth_ip': '授权服务IP地址',
                            'dns_ip': '域名IP地址',
                            'dns': 'DNS',
                            'auth_dns': '权威服务器',
                            'find_by_dns': '找到NS记录的DNS',
                            'cname': '域名的CNAME'
                        };
                        document.getElementById('node_name').value = clickedNode.label;
                        document.getElementById('group_name').value = groupMap[clickedNode.group] || clickedNode.group;
                    }
                });

                // 监听节点拖动事件
                network.on('dragStart', function (params) {
                    if (params.nodes.length > 0) {
                        const draggedNodeId = params.nodes[0];
                        network.storePositions();
                        const updatedNodes = visNodes.get({
                            filter: function (item) {
                                return item.id === draggedNodeId;
                            }
                        });

                        // 增加被拖动节点的连线长度
                        if (updatedNodes.length > 0) {
                            options.physics.barnesHut.springLength = 280;
                            network.setOptions(options);
                        }
                    }
                });
                // 拖动结束还原边的长度
                network.on('dragEnd', function (params) {
                    if (params.nodes.length > 0) {
                        const draggedNodeId = params.nodes[0];
                        network.storePositions();
                        const updatedNodes = visNodes.get({
                            filter: function (item) {
                                return item.id === draggedNodeId;
                            }
                        });

                        // 恢复其他节点的连线长度
                        if (updatedNodes.length > 0) {
                            options.physics.barnesHut.springLength = 200;
                            network.setOptions(options);
                        }
                    }
                });

                // 获取查询的服务器数目并更新页面
                updateServerCount();
            } else {
                console.error('There was an error!', xhr.responseText);
            }
        }
    };
    xhr.send(JSON.stringify({domain: domain}));
}

// 添加一个函数来获取服务器数目并更新页面
function updateServerCount() {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', '/server-count', true);
    xhr.onreadystatechange = function () {
        if (xhr.readyState === 4 && xhr.status === 200) {
            document.getElementById('server-count').textContent = JSON.parse(xhr.responseText).count;
        }
    };
    xhr.send();
}

function switchModel() {
    isAggregate = !isAggregate; // 点击之后首先变为true 代表聚合态
    const button = document.getElementById('switchButton');
    button.textContent = isAggregate ? '分离' : '聚合';

    if (isAggregate) {
        queryDomain01();
    } else {
        queryDomain();
    }
}

// 页面加载时获取一次服务器数目
window.onload = updateServerCount;