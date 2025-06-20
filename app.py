import streamlit as st
import numpy as np
import random
import time
from collections import deque
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# --- ゲームの設定 ---
MAP_WIDTH = 18
MAP_HEIGHT = 14
WALL = "🧱"
FLOOR = "⬛"
PLAYER = "🏃"
ONI = "👹"
KEY = "🔑"
EXIT_LOCKED = "🚪"
EXIT_UNLOCKED = "🟩"
OBSTACLE = "🌲"
TRAP = "🪤"
INITIAL_PLAYER_POS = [1, 1]
EXIT_POS = [MAP_WIDTH - 2, 1] # [16, 1]

# --- Google Sheets 連携 ---
def get_gspread_client():
    """StreamlitのSecretから認証情報を取得し、gspreadクライアントを返す"""
    try:
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception:
        return None

@st.cache_data(ttl=60) # 60秒間結果をキャッシュする
def get_ranking(_client):
    """スプレッドシートからランキングデータを取得・表示"""
    try:
        spreadsheet_key = st.secrets.spreadsheet_key
        sheet = _client.open_by_key(spreadsheet_key).sheet1 # キーで開くように変更
        records = sheet.get_all_records()
        if not records:
            return pd.DataFrame(columns=['Name', 'Difficulty', 'ClearCount'])
            
        df = pd.DataFrame(records)
        df['ClearCount'] = pd.to_numeric(df['ClearCount'])
        top_scores = df.loc[df.groupby('Name')['ClearCount'].idxmax()]
        ranking = top_scores.sort_values(by='ClearCount', ascending=False).head(5)
        return ranking[['Name', 'Difficulty', 'ClearCount']]
    except Exception as e:
        st.sidebar.warning(f"ランキング取得エラー: {e}")
        return pd.DataFrame()

def save_score(client, name, difficulty, clear_count):
    """スコアをスプレッドシートに保存"""
    try:
        spreadsheet_key = st.secrets.spreadsheet_key
        sheet = client.open_by_key(spreadsheet_key).sheet1 # キーで開くように変更
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([name, difficulty, clear_count, timestamp])
        # スコア保存後にキャッシュをクリア
        st.cache_data.clear()
    except Exception as e:
        st.sidebar.warning(f"スコア保存エラー: {e}")


def is_path_possible(game_map, start_pos, end_pos):
    """BFS (幅優先探索) を使って、スタートからゴールまでの道があるかチェック"""
    if not start_pos or not end_pos: return False
    queue = deque([start_pos])
    visited = {tuple(start_pos)}
    
    while queue:
        x, y = queue.popleft()
        if [x, y] == end_pos: return True
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if 0 <= ny < MAP_HEIGHT and 0 <= nx < MAP_WIDTH:
                if tuple([nx, ny]) not in visited and game_map[ny][nx] != WALL:
                    visited.add(tuple([nx, ny]))
                    queue.append([nx, ny])
    return False

def generate_map(clear_count):
    """壁、鍵、障害物をランダムに配置し、クリア可能なマップを生成する"""
    while True:
        game_map = np.full((MAP_HEIGHT, MAP_WIDTH), FLOOR, dtype=str)
        game_map[0, :] = WALL; game_map[-1, :] = WALL
        game_map[:, 0] = WALL; game_map[:, -1] = WALL
        possible_wall_positions = []
        for y in range(1, MAP_HEIGHT - 1):
            for x in range(1, MAP_WIDTH - 1):
                 if [x, y] not in [INITIAL_PLAYER_POS, EXIT_POS]:
                    possible_wall_positions.append([x, y])
        
        num_walls = 30
        if len(possible_wall_positions) >= num_walls:
            wall_positions = random.sample(possible_wall_positions, num_walls)
            for pos in wall_positions: game_map[pos[1]][pos[0]] = WALL

        possible_key_positions = []
        for y in range(1, MAP_HEIGHT - 1):
            for x in range(1, MAP_WIDTH - 1):
                if game_map[y][x] == FLOOR and [x,y] not in [INITIAL_PLAYER_POS, EXIT_POS]:
                    possible_key_positions.append([x, y])
        
        if not possible_key_positions: continue
        random.shuffle(possible_key_positions)
        
        key_pos = None
        for pos in possible_key_positions:
             if is_path_possible(game_map, INITIAL_PLAYER_POS, pos) and \
                is_path_possible(game_map, pos, EXIT_POS):
                key_pos = pos
                break
        
        if key_pos: break
            
    possible_obstacle_positions = []
    for y in range(1, MAP_HEIGHT - 1):
        for x in range(1, MAP_WIDTH - 1):
            if game_map[y][x] == FLOOR and [x, y] not in [INITIAL_PLAYER_POS, key_pos, EXIT_POS]:
                possible_obstacle_positions.append([x, y])
    
    num_obstacles = min(clear_count, 40)
    if num_obstacles > 0 and len(possible_obstacle_positions) >= num_obstacles:
        obstacle_positions = random.sample(possible_obstacle_positions, num_obstacles)
        for pos in obstacle_positions: game_map[pos[1]][pos[0]] = OBSTACLE

    return game_map.tolist(), key_pos

def initialize_game():
    """ゲームの状態を初期化する"""
    if 'game_started' not in st.session_state:
        if 'clear_count' not in st.session_state: st.session_state.clear_count = 0
        if 'difficulty' not in st.session_state: st.session_state.difficulty = "ふつう"
        if 'player_name' not in st.session_state: st.session_state.player_name = "名無し"

        game_map, key_pos = generate_map(st.session_state.clear_count)
        st.session_state.game_map = game_map
        st.session_state.key_pos = key_pos
        st.session_state.player_pos = list(INITIAL_PLAYER_POS)
        bottom_right_oni = [MAP_WIDTH - 2, MAP_HEIGHT - 2]
        bottom_left_oni = [1, MAP_HEIGHT - 2]
        st.session_state.oni_pos = random.choice([bottom_right_oni, bottom_left_oni])
        st.session_state.exit_pos = list(EXIT_POS)
        st.session_state.has_key = False
        st.session_state.game_over = False
        st.session_state.win = False
        st.session_state.message = "屋敷に閉じ込められた...。鍵を見つけて脱出しなければ。"
        st.session_state.turn_count = 0
        st.session_state.win_counted = False
        st.session_state.game_started = True
        st.session_state.start_time = time.time()
        st.session_state.end_time = None
        st.session_state.oni_last_move_time = time.time()
        
        st.session_state.player_trap_pos = None
        st.session_state.map_trap_pos = None
        st.session_state.oni_stopped_turns = 0
        if st.session_state.difficulty == "むずかしい":
            st.session_state.trap_count = 1
            possible_trap_positions = []
            for y in range(1, MAP_HEIGHT - 1):
                for x in range(1, MAP_WIDTH - 1):
                    if st.session_state.game_map[y][x] == FLOOR and [x,y] not in [st.session_state.player_pos, st.session_state.oni_pos, st.session_state.key_pos, st.session_state.exit_pos]:
                        possible_trap_positions.append([x, y])
            if possible_trap_positions: st.session_state.map_trap_pos = random.choice(possible_trap_positions)
        else: st.session_state.trap_count = 0

def display_map():
    display_map_data = [row[:] for row in st.session_state.game_map]
    px, py = st.session_state.player_pos
    ox, oy = st.session_state.oni_pos
    if st.session_state.player_trap_pos:
        tx, ty = st.session_state.player_trap_pos
        if [tx, ty] != [px, py] and [tx, ty] != [ox, oy]: display_map_data[ty][tx] = TRAP
    if st.session_state.map_trap_pos:
        tx, ty = st.session_state.map_trap_pos
        if [tx, ty] != [px, py] and [tx, ty] != [ox, oy]: display_map_data[ty][tx] = TRAP
    if st.session_state.key_pos:
        kx, ky = st.session_state.key_pos
        display_map_data[ky][kx] = KEY
    ex, ey = st.session_state.exit_pos
    display_map_data[py][px] = PLAYER
    display_map_data[oy][ox] = ONI
    exit_icon = EXIT_UNLOCKED if st.session_state.has_key else EXIT_LOCKED
    display_map_data[ey][ex] = exit_icon
    map_str = "\n".join(["".join(row) for row in display_map_data])
    st.code(map_str, language=None)

def move_player(dx, dy):
    if st.session_state.game_over or st.session_state.win: return
    px, py = st.session_state.player_pos
    new_px, new_py = px + dx, py + dy
    if st.session_state.game_map[new_py][new_px] not in [WALL, OBSTACLE]:
        st.session_state.player_pos = [new_px, new_py]
        st.session_state.message = ""
        check_events()

def handle_bulk_move(commands):
    for command in commands.lower():
        if st.session_state.game_over or st.session_state.win: break
        dx, dy = 0, 0
        if command == 'l': dx = -1
        elif command == 'r': dx = 1
        elif command == 'u': dy = -1
        elif command == 'd': dy = 1
        else: continue
        px, py = st.session_state.player_pos
        new_px, new_py = px + dx, py + dy
        if st.session_state.game_map[new_py][new_px] not in [WALL, OBSTACLE]:
            st.session_state.player_pos = [new_px, new_py]
            check_events()
        else:
            st.session_state.message = "一括移動中に壁にぶつかり停止しました。"
            break
            
def _move_oni_one_step():
    px, py = st.session_state.player_pos
    ox, oy = st.session_state.oni_pos
    new_ox, new_oy = ox, oy
    dist_x, dist_y = px - ox, py - oy
    impassable = [WALL]
    if abs(dist_x) > abs(dist_y):
        if dist_x > 0 and st.session_state.game_map[oy][ox + 1] not in impassable: new_ox += 1
        elif dist_x < 0 and st.session_state.game_map[oy][ox - 1] not in impassable: new_ox -= 1
        elif dist_y > 0 and st.session_state.game_map[oy + 1][ox] not in impassable: new_oy += 1
        elif dist_y < 0 and st.session_state.game_map[oy - 1][ox] not in impassable: new_oy -= 1
    else:
        if dist_y > 0 and st.session_state.game_map[oy + 1][ox] not in impassable: new_oy += 1
        elif dist_y < 0 and st.session_state.game_map[oy - 1][ox] not in impassable: new_oy -= 1
        elif dist_x > 0 and st.session_state.game_map[oy][ox + 1] not in impassable: new_ox += 1
        elif dist_x < 0 and st.session_state.game_map[oy][ox - 1] not in impassable: new_ox -= 1
    st.session_state.oni_pos = [new_ox, new_oy]

def check_oni_trap_interaction():
    oni_pos = st.session_state.oni_pos
    trapped = False
    if st.session_state.player_trap_pos and oni_pos == st.session_state.player_trap_pos:
        st.session_state.player_trap_pos = None; trapped = True
    elif st.session_state.map_trap_pos and oni_pos == st.session_state.map_trap_pos:
        st.session_state.map_trap_pos = None; trapped = True
    if trapped:
        st.session_state.oni_stopped_turns = 3
        st.session_state.message = f"鬼が罠にかかった！ {st.session_state.oni_stopped_turns}ターン動けない。"

def move_oni():
    if st.session_state.oni_stopped_turns > 0:
        st.session_state.oni_stopped_turns -= 1
        if st.session_state.oni_stopped_turns > 0:
            st.session_state.message = f"鬼は罠にはまっている！あと{st.session_state.oni_stopped_turns}ターンは動けない。"
        else: st.session_state.message = "鬼が罠から抜け出した！"
        return
    difficulty = st.session_state.difficulty
    if difficulty == "やさしい" or difficulty == "ふつう":
        _move_oni_one_step()
    elif difficulty == "むずかしい":
        _move_oni_one_step()
        if st.session_state.player_pos == st.session_state.oni_pos: check_events(); return
        _move_oni_one_step()
    check_oni_trap_interaction()

def check_events():
    if st.session_state.player_pos == st.session_state.oni_pos:
        st.session_state.game_over = True
        st.session_state.message = "鬼に捕まってしまった...。"
        if not st.session_state.end_time: st.session_state.end_time = time.time()
        return
    if st.session_state.key_pos and st.session_state.player_pos == st.session_state.key_pos:
        st.session_state.has_key = True; st.session_state.key_pos = None
        st.session_state.message = "鍵を手に入れた！出口を探そう。"
        return
    if st.session_state.player_pos == st.session_state.exit_pos:
        if st.session_state.has_key:
            st.session_state.win = True
            st.session_state.message = "脱出に成功した！おめでとう！"
            if not st.session_state.win_counted:
                st.session_state.clear_count += 1
                st.session_state.win_counted = True
                client = get_gspread_client()
                if client:
                    save_score(client, st.session_state.player_name, st.session_state.difficulty, st.session_state.clear_count)
            if not st.session_state.end_time: st.session_state.end_time = time.time()
        else: st.session_state.message = "鍵がかかっている...。鍵を探さなければ。"

def automatic_oni_move():
    if st.session_state.game_over or st.session_state.win: return
    interval = 1.0
    if st.session_state.difficulty == 'やさしい': interval = 1.5
    elif st.session_state.difficulty == 'むずかしい': interval = 0.8
    if time.time() - st.session_state.oni_last_move_time > interval:
        move_oni()
        check_events()
        st.session_state.oni_last_move_time = time.time()

def force_game_reset():
    st.session_state.pop('game_started', None)
    
def restart_game():
    force_game_reset(); st.rerun()

# --- メインのUI ---
st.set_page_config(page_title="Streamlit 青鬼")
initialize_game()
automatic_oni_move()

# --- サイドバー (設定と情報) ---
with st.sidebar:
    st.subheader("ランキング")
    gspread_client = get_gspread_client()
    if gspread_client:
        ranking_df = get_ranking(gspread_client)
        st.dataframe(ranking_df, hide_index=True)
    else:
        st.info("ランキング機能を利用するには、secrets.tomlの設定が必要です。")

    st.subheader("今回の名前")
    st.text_input("名前", key="player_name", label_visibility="collapsed")
    st.write("---")
    
    if 'start_time' in st.session_state:
        elapsed_time = (st.session_state.end_time or time.time()) - st.session_state.start_time
        minutes, seconds = int(elapsed_time // 60), int(elapsed_time % 60)
        st.write(f"**経過時間: {minutes:02d}:{seconds:02d}**")
    st.write("---")
    st.selectbox("難易度", ("やさしい", "ふつう", "むずかしい"), key='difficulty', 
                 disabled=(st.session_state.turn_count > 0), on_change=force_game_reset)
    st.write(f"**クリア回数: {st.session_state.clear_count}**")
    st.write(f"鍵の所持: {'あり' if st.session_state.has_key else 'なし'}")
    if st.session_state.difficulty == "むずかしい":
        st.write(f"**設置可能罠: {st.session_state.trap_count}**")
    st.write("---")
    st.write("**一括移動** (l:左, r:右, u:上, d:下)")
    command_input = st.text_input("コマンド:", key="command_input", label_visibility="collapsed")
    if st.button("一括移動を実行"): handle_bulk_move(command_input); st.rerun()
    st.write("---")
    with st.expander("ゲームのルール (Q&A)", expanded=False):
        st.markdown("""
        **Q. 目的は？** A. 鬼（👹）に捕まらずに鍵（🔑）を見つけ、出口（🚪）から脱出することです。
        **Q. 操作方法は？** A. メイン画面下部のボタンか、サイドバーの一括移動を使います。
        **Q. リアルタイム制とは？** A. あなたが何もしなくても、鬼が自動で動きます。難易度によって速さが変わります。
        """)
    with st.expander("障害物（🌲）について", expanded=False):
        st.markdown("**Q. 障害物（🌲）って何？** A. クリアごとに増える壁です。プレイヤーは通れませんが、鬼は通り抜けます。")
    with st.expander("罠（🪤）について", expanded=False):
        st.markdown("""
        **Q. 罠（🪤）って何？** A. 鬼を3ターン止められるアイテムです。「むずかしい」モードでのみ使えます。
        **Q. どうやって使うの？** A. 「🪤」ボタンで現在地に設置できます。「むずかしい」では最初からマップに1つ、自分で置けるのが1つあります。
        """)

# --- メイン画面 ---
st.markdown("""
<style>
h1 {font-size: 1.5rem;}
div[data-testid="stAlert"] {
    min-height: 4em; /* メッセージ欄の高さを固定 */
    display: flex;
    align-items: center;
}
</style>
""", unsafe_allow_html=True)
st.title("青鬼風ゲーム")
st.caption("鬼から逃げながら鍵を見つけ、屋敷から脱出せよ！")
if st.session_state.game_over: st.error(st.session_state.message)
elif st.session_state.win: st.success(st.session_state.message)
else: st.info(st.session_state.message)
display_map()

# --- 操作ボタン ---
st.write("---")
st.write("**操作**")
is_control_disabled = st.session_state.game_over or st.session_state.win
cols = st.columns(10)
with cols[0]:
    if st.button("◀", use_container_width=True, disabled=is_control_disabled): move_player(-1, 0); st.rerun()
with cols[1]:
    if st.button("▲", use_container_width=True, disabled=is_control_disabled): move_player(0, -1); st.rerun()
with cols[2]:
    if st.button("▼", use_container_width=True, disabled=is_control_disabled): move_player(0, 1); st.rerun()
with cols[3]:
    if st.button("▶", use_container_width=True, disabled=is_control_disabled): move_player(1, 0); st.rerun()
with cols[4]:
    if st.session_state.difficulty == "むずかしい":
        trap_button_disabled = (st.session_state.trap_count <= 0 or st.session_state.player_trap_pos is not None or is_control_disabled)
        if st.button("🪤", use_container_width=True, disabled=trap_button_disabled, help="罠を設置"):
            st.session_state.player_trap_pos = list(st.session_state.player_pos)
            st.session_state.trap_count -= 1
            st.session_state.message = "床に罠を設置した。"
            st.rerun()
st.write("") 
if st.button("リスタート", use_container_width=True): restart_game()

# --- リアルタイム更新 ---
if not st.session_state.game_over and not st.session_state.win:
    time.sleep(0.1)
    st.rerun()
