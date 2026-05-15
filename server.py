"""
五子棋联机对战服务器
使用 FastAPI + WebSocket 实现实时对战
"""

import asyncio
import json
import random
import string
from typing import Dict, Set
from dataclasses import dataclass, field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="Gomoku Online")


@dataclass
class Player:
    websocket: WebSocket
    player_id: str
    name: str = ""
    role: str = ""  # "black" or "white"


@dataclass
class Room:
    code: str
    players: Dict[str, Player] = field(default_factory=dict)
    board: list = field(default_factory=lambda: [[None] * 15 for _ in range(15)])
    current_turn: str = "black"
    game_started: bool = False
    game_over: bool = False


# 存储所有房间
rooms: Dict[str, Room] = {}


def generate_player_id() -> str:
    """生成唯一玩家ID"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))


def generate_room_code() -> str:
    """生成6位房间码"""
    return ''.join(random.choices(string.digits, k=6))


@app.get("/")
async def get_index():
    """提供前端页面"""
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    """WebSocket连接处理"""
    player_id = generate_player_id()
    player = Player(websocket=websocket, player_id=player_id)
    
    await websocket.accept()
    
    # 获取或创建房间
    if room_code not in rooms:
        rooms[room_code] = Room(code=room_code)
    
    room = rooms[room_code]
    room.players[player_id] = player
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await handle_message(room, player, message)
            
    except WebSocketDisconnect:
        # 玩家断开连接
        if player_id in room.players:
            del room.players[player_id]
            
            # 通知其他玩家
            for p in room.players.values():
                try:
                    await p.websocket.send_json({
                        "type": "player_left",
                        "playerId": player_id
                    })
                except:
                    pass
            
            # 如果房间空了，删除房间
            if len(room.players) == 0:
                del rooms[room_code]
                print(f"房间 {room_code} 已删除")


async def handle_message(room: Room, player: Player, message: dict):
    """处理玩家消息"""
    msg_type = message.get("type")
    
    if msg_type == "create":
        # 创建房间
        player.name = message.get("playerName", "玩家")
        player.role = "black"
        room.current_turn = "black"
        
        await player.websocket.send_json({
            "type": "joined",
            "playerId": player.player_id,
            "role": "black",
            "playerId": player.player_id,
            "blackPlayer": player.name,
            "whitePlayer": None
        })
        
        print(f"玩家 {player.name} 创建了房间 {room.code}")
    
    elif msg_type == "join":
        # 加入房间
        player.name = message.get("playerName", "玩家")
        
        # 检查房间状态
        if room.game_started:
            await player.websocket.send_json({
                "type": "error",
                "message": "房间游戏已开始"
            })
            return
        
        # 分配白方
        player.role = "white"
        room.game_started = True
        room.current_turn = "black"
        
        # 获取黑方玩家
        black_player = None
        for p in room.players.values():
            if p.role == "black":
                black_player = p
                break
        
        # 通知黑方有新玩家加入
        if black_player:
            await black_player.websocket.send_json({
                "type": "player_joined",
                "playerName": player.name,
                "role": "white"
            })
        
        # 通知白方
        await player.websocket.send_json({
            "type": "joined",
            "playerId": player.player_id,
            "role": "white",
            "blackPlayer": black_player.name if black_player else "黑方",
            "whitePlayer": player.name
        })
        
        print(f"玩家 {player.name} 加入了房间 {room.code}")
    
    elif msg_type == "move":
        # 下棋
        if room.game_over or not room.game_started:
            return
        
        if player.role != room.current_turn:
            return
        
        row = message.get("row")
        col = message.get("col")
        
        if row is None or col is None:
            return
        
        if row < 0 or row >= 15 or col < 0 or col >= 15:
            return
        
        if room.board[row][col] is not None:
            return
        
        # 落子
        room.board[row][col] = player.role
        
        # 广播给所有玩家
        for p in room.players.values():
            await p.websocket.send_json({
                "type": "move",
                "row": row,
                "col": col,
                "player": player.role
            })
        
        # 检查胜负
        if check_win(room.board, row, col, player.role):
            room.game_over = True
            for p in room.players.values():
                await p.websocket.send_json({
                    "type": "game_over",
                    "winner": player.role
                })
        else:
            # 换手
            room.current_turn = "white" if player.role == "black" else "black"
    
    elif msg_type == "restart":
        # 重新开始
        room.board = [[None] * 15 for _ in range(15)]
        room.game_over = False
        room.current_turn = "black"
        
        for p in room.players.values():
            await p.websocket.send_json({
                "type": "restart"
            })
    
    elif msg_type == "leave":
        # 离开房间
        if player.player_id in room.players:
            del room.players[player.player_id]
            
            for p in room.players.values():
                await p.websocket.send_json({
                    "type": "player_left",
                    "playerId": player.player_id
                })
            
            if len(room.players) == 0:
                del rooms[player.player_id]


def check_win(board: list, row: int, col: int, player: str) -> bool:
    """检查是否五子连珠"""
    directions = [
        [(0, 1), (0, -1)],   # 水平
        [(1, 0), (-1, 0)],   # 垂直
        [(1, 1), (-1, -1)], # 对角线
        [(1, -1), (-1, 1)]  # 反对角线
    ]
    
    for (d1, d2) in directions:
        count = 1
        
        # 方向1
        for i in range(1, 5):
            r, c = row + d1[0] * i, col + d1[1] * i
            if 0 <= r < 15 and 0 <= c < 15 and board[r][c] == player:
                count += 1
            else:
                break
        
        # 方向2
        for i in range(1, 5):
            r, c = row + d2[0] * i, col + d2[1] * i
            if 0 <= r < 15 and 0 <= c < 15 and board[r][c] == player:
                count += 1
            else:
                break
        
        if count >= 5:
            return True
    
    return False


@app.get("/rooms")
async def list_rooms():
    """列出所有房间（调试用）"""
    return {
        "count": len(rooms),
        "rooms": [
            {
                "code": code,
                "players": len(room.players),
                "game_started": room.game_started
            }
            for code, room in rooms.items()
        ]
    }


if __name__ == "__main__":
    print("=" * 50)
    print("  五子棋联机对战服务器")
    print("  访问 http://localhost:8000 开始游戏")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
