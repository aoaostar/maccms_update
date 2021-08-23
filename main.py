# -*- coding: utf-8 -*-
# !/usr/bin/python3
import errno
import os
import shutil
import stat
import sys
import time
import zipfile
from concurrent.futures import wait, ALL_COMPLETED, ThreadPoolExecutor

import requests


# 获取运行目录
def get_running_path(path=''):
    path = os.sep + path.lstrip("/").lstrip("\\") + os.sep
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable) + path
    elif __file__:
        return os.path.dirname(__file__) + path


TEMP_PATH = get_running_path('temp')
BACKUP_PATH = get_running_path('backup')
##################################################################

# 需要升级的路径
UPDATE_PATH = [
    'D:\Workspace\PHP\maccms - 副本',
]
# 需要备份的路径
NEED_BACKUP_PATH = [
    '/application/data/install/install.lock',
    '/application/database.php',
    '/application/extra/',
    '/template/',
    '/upload/',
]
# 在需要备份的路径中需要跳过的文件
WITHOU_BACKUP_PATH = [
    '/application/extra/version.php',
]
# 需要安装的插件目录
PLUGIN_PATH = [

]
# 下载包的github的仓库
GITHUB_INFO = {
    'user': 'magicblack',
    'repo': 'maccms10',
}
# 多线程备份文件的线程数，按自己服务器来，小文件填个几百没问题，单个几个GB的就别了
BACKUP_MAX_WORKERS = 50

# copy 或者 move
# move是剪切会快一点，不过move无法重复运行，必须一次到位，中断了得自行去backup文件夹内使用备份文件恢复！
# copy是拷贝会慢一点，不过copy会保留文件到backup文件夹，保险！推荐使用该方式
BACKUP_MODE = 'copy'

##################################################################

def get_release_info(user, repo):
    print('正在请求：https://api.github.com/repos/%s/%s/releases/latest' % (user, repo))
    requests_get = requests.get('https://api.github.com/repos/%s/%s/releases/latest' % (user, repo))
    if requests_get.status_code != 200:
        print("release_url：%d" % requests_get.status_code)
        return False
    requests_get_json = requests_get.json()
    download_url = requests_get_json.get('zipball_url')
    tag_name = requests_get_json.get('tag_name')
    print("获取下载地址成功：%s" % download_url)
    print("当前版本：%s" % tag_name)
    return requests_get_json


def download(download_url, tag_name):
    print('正在下载：%s' % download_url)
    download_url_get = requests.get(download_url)
    zip_filename = "%s.zip" % tag_name
    if download_url_get.status_code != 200:
        print("download_url：%d" % download_url_get.status_code)
        return False

    try:
        with open(TEMP_PATH + zip_filename, "wb+") as f:
            f.write(download_url_get.content)
            f.flush()
    except Exception as e:
        print(e)
        return False
    print('下载成功：%s' % (TEMP_PATH + zip_filename))
    return TEMP_PATH + zip_filename


def unzip_file(fz_name, path):
    print("正在解压 %s 至 %s" % (fz_name, path))
    if not os.path.exists(path):
        os.makedirs(path)
    if zipfile.is_zipfile(fz_name):  # 检查是否为zip文件
        with zipfile.ZipFile(fz_name, 'r') as zipf:
            zipf.extractall(path)
            print("解压成功 %s" % fz_name)
            return True

    return False


def qualify_path(path):
    if not path:
        return ''
    return path.replace('/', os.sep).replace('\\\\', os.sep).rstrip(os.sep) + os.sep


def get_all_file_relative(path):
    result = []
    if not os.path.exists(path):
        return result
    get_dir = os.listdir(path)
    for i in get_dir:
        sub_dir = os.path.join(path, i)
        if os.path.isdir(sub_dir):
            all_file = get_all_file_relative(sub_dir)
            all_file = map(lambda x: i + os.sep + x, all_file)
            result.extend(all_file)
        else:
            result.append(i)
    return result


def backup(src, dict):
    getattr(shutil, BACKUP_MODE)(src, dict)


def recursive_overwrite(src, dist):
    def func(src, dist):
        if os.path.isdir(src):
            if not os.path.isdir(dist):
                os.makedirs(dist)
            files = os.listdir(src)
            for f in files:
                func(os.path.join(src, f), os.path.join(dist, f))
        else:
            res = executor.submit(backup, src, dist)
            all_task.append(res)
            print("写入成功：%s" % dist)

    with ThreadPoolExecutor(max_workers=BACKUP_MAX_WORKERS) as executor:
        all_task = []
        func(src, dist)
        wait(all_task, return_when=ALL_COMPLETED)


def handleRemoveReadonly(func, path, exc):
    excvalue = exc[1]
    if os.path.basename(path) == '.user.ini':
        os.system("chattr -i '" + path + "'")
    if func in (os.unlink, os.rmdir, os.remove) and (excvalue.errno == errno.EACCES or excvalue.errno == errno.EPERM):
        os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)  # 0777
        func(path)
    else:
        raise


def over(message=None):
    if not message is None:
        print(message)
    os._exit(0)


def main(app_path):
    print("当前升级目录：%s" % app_path)
    backup_path = BACKUP_PATH + os.path.basename(app_path) + "_%s" % time.strftime("%Y%m%d_%H%M%S")
    # 备份配置文件
    if os.path.exists(backup_path):
        shutil.rmtree(backup_path)
        os.makedirs(backup_path)
    with ThreadPoolExecutor(max_workers=BACKUP_MAX_WORKERS) as executor:
        all_task = []

        def func(need_backup_path, without_backup_path, root_path, backup_path, parent_path=''):
            for item in need_backup_path:

                if item in without_backup_path or parent_path + item in without_backup_path:
                    print("该文件已存在 WITHOU_BACKUP_PATH，已跳过%s" % item)
                    continue
                if os.path.exists(root_path + item):
                    if not os.path.exists(os.path.dirname(backup_path + os.sep + item)):
                        os.makedirs(os.path.dirname(backup_path + os.sep + item))
                    if not os.path.isdir(root_path + item):
                        backup(root_path + item, backup_path + os.sep + item)
                        print("备份成功：%s" % root_path + item)
                    else:
                        list_path = get_all_file_relative(root_path + item)

                        res = executor.submit(func, list_path, without_backup_path, root_path + item,
                                              backup_path + item,
                                              item)
                        all_task.append(res)

        func(NEED_BACKUP_PATH, WITHOU_BACKUP_PATH, app_path, backup_path)
        wait(all_task, return_when=ALL_COMPLETED)
    print('备份文件成功！')
    # 获取下载地址
    release_info = get_release_info(GITHUB_INFO.get('user'), GITHUB_INFO.get('repo'))
    if not release_info:
        over('get_release_info failed!')
    #  下载文件包
    if os.path.exists('%s/release/%s.zip' % (TEMP_PATH, release_info.get('tag_name'))):
        print("当前版本已存在更新文件，无需重复下载")
    else:
        download_res = download(release_info.get('zipball_url'), release_info.get('tag_name'))
        if not download_res:
            over('download failed!')

        unzip_file_res = unzip_file(download_res, TEMP_PATH + '/release')
        if not unzip_file_res:
            over('unzip_file failed!')
    # 删除旧文件
    print("正在删除旧文件")
    shutil.rmtree(app_path, ignore_errors=False, onerror=handleRemoveReadonly)
    print("删除旧文件成功！")
    # 迁移文件
    release_dir = '%s/release/%s' % (TEMP_PATH, os.listdir('%s/release' % TEMP_PATH)[0])
    print("正在覆盖备份文件到新版文件中")
    recursive_overwrite(backup_path, release_dir)
    print("覆盖备份文件文件到新版文件中成功！")
    print("正在覆盖新版文件到程序目录")
    recursive_overwrite(release_dir, app_path)
    print("覆盖新版文件到程序目录成功！")
    os.system('chown -R www:www ' + app_path)
    print("正在安装插件")
    for item in PLUGIN_PATH:
        recursive_overwrite(item, app_path)
    print("安装插件成功")
    print("应用升级成功：%s" % app_path)
    return True


if __name__ == '__main__':
    # 清除temp目录
    if os.path.exists(TEMP_PATH):
        shutil.rmtree(TEMP_PATH)
    os.makedirs(TEMP_PATH)
    for item in UPDATE_PATH:
        # 清理旧的文件
        release_path = TEMP_PATH + 'release'
        if os.path.exists(release_path):
            shutil.rmtree(release_path)

        if not os.path.exists(item):
            print("目录不存在")
            continue
        main(item)

    # 清除temp目录
    if os.path.exists(TEMP_PATH):
        shutil.rmtree(TEMP_PATH)
