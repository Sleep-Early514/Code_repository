from bilibili_api import video, sync, Credential
import requests
import os
import subprocess
import json
import asyncio

class BilibiliAudioDownloader:
    def __init__(self, sessdata=None, bili_jct=None, buvid3=None):
        """
        初始化下载器
        :param sessdata: 登录凭证（可选）
        :param bili_jct: CSRF token（可选）
        :param buvid3: 设备ID（可选）
        """
        self.credential = None
        if sessdata or bili_jct or buvid3:
            self.credential = Credential(
                sessdata=sessdata or "",
                bili_jct=bili_jct or "",
                buvid3=buvid3 or ""
            )
        
    def get_video_info(self, bvid):
        """获取视频信息"""
        v = video.Video(bvid=bvid, credential=self.credential)
        info = sync(v.get_info())
        return info
    
    def get_play_info(self, bvid):
        """获取播放信息（修复的方法）"""
        try:
            # 获取视频信息以得到cid
            v = video.Video(bvid=bvid, credential=self.credential)
            video_info = sync(v.get_info())
            
            # 获取视频的cid（分P的ID）
            cid = None
            if 'pages' in video_info and len(video_info['pages']) > 0:
                # 使用第一个分P的cid
                cid = video_info['pages'][0]['cid']
            elif 'cid' in video_info:
                cid = video_info['cid']
            
            if not cid:
                print("无法获取视频cid")
                return None
            
            print(f"视频CID: {cid}")
            
            # 使用cid获取下载链接
            try:
                # 方法1: 使用get_download_url（需要cid参数）
                play_info = sync(v.get_download_url(cid=cid))
                return play_info
            except Exception as e:
                print(f"使用get_download_url失败: {e}")
                
                # 方法2: 使用备用API
                return self.get_play_info_backup(bvid, cid)
                
        except Exception as e:
            print(f"获取播放信息失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_play_info_backup(self, bvid, cid):
        """备用方法获取播放信息（直接调用B站API）"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.bilibili.com'
            }
            
            # B站API获取播放地址
            play_url = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=0&fnval=16&fourk=1"
            response = requests.get(play_url, headers=headers)
            play_data = response.json()
            
            if play_data['code'] == 0:
                return play_data['data']
            else:
                print(f"API返回错误: {play_data['message']}")
                return None
                
        except Exception as e:
            print(f"备用方法失败: {e}")
            return None
    
    def get_audio_url(self, bvid):
        """获取音频下载链接"""
        play_info = self.get_play_info(bvid)
        
        if not play_info:
            return None
        
        # 调试：打印play_info结构
        # print(f"播放信息结构: {json.dumps(play_info, indent=2, ensure_ascii=False)[:500]}...")
        
        # 尝试不同的数据结构
        if 'dash' in play_info:
            # 新版本API格式
            dash_data = play_info['dash']
            if 'audio' in dash_data and dash_data['audio']:
                # 选择音质最好的音频
                audio_streams = dash_data['audio']
                # 按码率排序，选择码率最高的
                audio_streams.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
                return audio_streams[0]['baseUrl']
        
        # 如果没有找到dash格式，尝试备用格式
        elif 'durl' in play_info and play_info['durl']:
            # 旧格式，可能包含音视频混合
            return play_info['durl'][0]['url']
        
        print("未找到音频流")
        return None
    
    def download_audio(self, bvid, output_path=None):
        """
        下载音频文件
        :param bvid: 视频BV号
        :param output_path: 输出路径，None则自动生成
        """
        try:
            # 获取视频信息
            info = self.get_video_info(bvid)
            print(f"视频标题: {info['title']}")
            print(f"视频作者: {info['owner']['name']}")
            print(f"视频时长: {info['duration']}秒")
            
            # 获取音频URL
            audio_url = self.get_audio_url(bvid)
            if not audio_url:
                print("无法获取音频URL")
                return False
            
            print(f"找到音频流")
            
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.bilibili.com',
                'Origin': 'https://www.bilibili.com'
            }
            
            # 设置输出文件名
            if not output_path:
                # 清理文件名中的非法字符
                import re
                safe_title = re.sub(r'[\\/*?:"<>|]', "", info['title'])
                if len(safe_title) > 100:
                    safe_title = safe_title[:100]
                output_path = f"{safe_title}.m4a"
            
            print(f"正在下载到: {output_path}")
            
            # 下载音频文件（使用流式下载）
            response = requests.get(audio_url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\r下载进度: {progress:.1f}% ({downloaded}/{total_size} bytes)", end='')
            
            print(f"\n音频已保存到: {output_path}")
            
            # 自动转换为MP3格式
            self.convert_to_mp3(output_path)
            
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            return False
        except Exception as e:
            print(f"下载过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def convert_to_mp3(self, audio_file):
        """将音频文件转换为MP3格式（需要安装ffmpeg）"""
        try:
            if not os.path.exists(audio_file):
                print(f"文件不存在: {audio_file}")
                return
            
            # 如果是m4a格式，直接重命名为mp3
            if audio_file.endswith('.m4a'):
                mp3_file = audio_file.replace('.m4a', '.mp3')
                os.rename(audio_file, mp3_file)
                print(f"已将M4A文件重命名为MP3: {mp3_file}")
                return
            
            mp3_file = os.path.splitext(audio_file)[0] + '.mp3'
            
            # 检查ffmpeg是否可用
            try:
                result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception("ffmpeg不可用")
            except:
                print("未找到ffmpeg，尝试重命名文件...")
                # 尝试直接重命名
                if audio_file != mp3_file:
                    os.rename(audio_file, mp3_file)
                    print(f"已重命名为: {mp3_file}")
                return
            
            print("正在转换为MP3...")
            
            # 使用ffmpeg转换
            command = [
                'ffmpeg', '-i', audio_file,
                '-acodec', 'libmp3lame',
                '-ab', '192k',
                '-vn',  # 只处理音频
                '-y',  # 覆盖已存在文件
                mp3_file
            ]
            
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"已转换为MP3: {mp3_file}")
                # 删除原始文件
                os.remove(audio_file)
                print("原始文件已删除")
            else:
                print(f"转换失败: {result.stderr}")
                # 如果转换失败，尝试重命名
                if audio_file.endswith(('.m4a', '.aac')):
                    os.rename(audio_file, mp3_file)
                    print(f"已将文件重命名为MP3: {mp3_file}")
            
        except Exception as e:
            print(f"转换失败: {e}")

def main():
    """主函数"""
    print("=== B站音频下载器 ===")
    print("1. 下载单个视频音频")
    print("2. 批量下载")
    print("3. 设置登录凭证（可选）")
    
    choice = input("请选择操作 (1/2/3): ")
    
    downloader = BilibiliAudioDownloader()
    
    if choice == '3':
        print("\n=== 设置登录凭证 ===")
        print("注意：只有在需要下载会员或需要登录的视频时才需要设置")
        print("获取方法：在B站网页按F12打开开发者工具，Application标签页，Cookies中找到对应值")
        sessdata = input("SESSDATA (留空跳过): ")
        bili_jct = input("bili_jct (留空跳过): ")
        buvid3 = input("buvid3 (留空跳过): ")
        
        if sessdata or bili_jct or buvid3:
            downloader = BilibiliAudioDownloader(sessdata, bili_jct, buvid3)
            print("登录凭证已设置")
    
    if choice == '1':
        bvid = input("请输入B站视频BV号（例如 BV1xx411c7mD）: ")
        if not bvid.startswith('BV'):
            print("无效的BV号，请确保以BV开头")
            return
        
        # 添加https://前缀如果用户没有添加
        if not bvid.startswith('http'):
            bvid = bvid.strip()
        else:
            # 从URL中提取BV号
            import re
            match = re.search(r'BV[0-9A-Za-z]{10}', bvid)
            if match:
                bvid = match.group(0)
            else:
                print("无法从URL中提取BV号")
                return
        
        downloader.download_audio(bvid)
    
    elif choice == '2':
        bvid_list = input("请输入BV号列表，用逗号分隔: ").split(',')
        bvid_list = [bvid.strip() for bvid in bvid_list if bvid.strip()]
        
        for bvid in bvid_list:
            if not bvid.startswith('BV'):
                print(f"跳过无效的BV号: {bvid}")
                continue
            
            print(f"\n{'='*50}")
            print(f"开始下载 {bvid}")
            print('='*50)
            success = downloader.download_audio(bvid)
            if success:
                print(f"下载完成: {bvid}")
            else:
                print(f"下载失败: {bvid}")

if __name__ == "__main__":
    main()
