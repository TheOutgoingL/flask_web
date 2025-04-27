# -*- coding: utf-8 -*-
# @Time    : 2024/5/26 上午10:16
# @Author  : lyx
# @File    : dbTest.py

# import pymysql
# from flask_sqlalchemy import SQLAlchemy
#
# # MySQL所在主机名
# HOSTNAME = "127.0.0.1"
# # MySQL监听的端口号，默认3306
# PORT = 3306
# # 连接MySQL的用户名，自己设置
# USERNAME = "root"
# # 连接MySQL的密码，自己设置
# PASSWORD = "liu2568910969"
# # MySQL上创建的数据库名称
# DATABASE = "database_learn"
# # 通过修改以下代码来操作不同的SQL比写原生SQL简单很多 --》通过ORM可以实现从底层更改使用的SQL
# app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{USERNAME}:{PASSWORD}@{HOSTNAME}:{PORT}/{DATABASE}?charset=utf8mb4"
#
# # 为了使用类SQLAlchemy封装的功能，我们需要创建一个类SQLAlchemy的实例对象，将它命名为db，将flask的实例对象app作为参数传给SQLAlchemy，是为了将db和app联系起来，这样就能调用相关功能了。
# db = SQLAlchemy(app)
#
# with app.app_context():
#     with db.engine.connect() as conn:
#         rs = conn.execute("select 1")
#         print(rs.fetchone())
#

    # 配置数据库连接
    # password = quote_plus('cnic@2023')
    # app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:{password}@localhost:33333/flask_DNSInfo'
from flask_sqlalchemy import SQLAlchemy
from flask import Flask
from sqlalchemy import text
from urllib.parse import quote_plus

app = Flask(__name__)
password = quote_plus('cnic@2023')
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:{password}@localhost:33333/flask_DNSInfo'

# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:liu2568910969@localhost/database_learn'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

def clear_domain_query_table():
    try:
        # 使用 text() 包裹原生 SQL 语句
        db.session.execute(text('TRUNCATE TABLE domain_query'))
        db.session.commit()
        print("表 domain_query 已成功清空。")
    except Exception as e:
        db.session.rollback()
        print(f"发生错误: {e}")

if __name__ == "__main__":
    # 创建应用上下文
    with app.app_context():
        clear_domain_query_table()


