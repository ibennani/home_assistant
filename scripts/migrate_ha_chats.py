#!/usr/bin/env python3
"""Migrate archived HA chats from granskningsverktyget to home_assistant workspace."""
import sqlite3
import json
import os
import shutil
from datetime import datetime

GLOBAL_DB = r'C:\Users\iliben\AppData\Roaming\Cursor\User\globalStorage\state.vscdb'
SOURCE_TRANSCRIPTS = r'C:\Users\iliben\.cursor\projects\c-kod-granskningsverktyget-sessionversion\agent-transcripts'
TARGET_TRANSCRIPTS = r'C:\Users\iliben\.cursor\projects\c-kod-home-assistant\agent-transcripts'
BACKUP_JSON = r'C:\kod\home_assistant\scripts\_ha_chat_migration_backup.json'

TARGET_WS_ID = 'd62e339d35b1d015f66570bcb8073c50'
SOURCE_WS_ID = 'fabb630ac7b59062545328b868b6cf98'

TARGET_WS_IDENTIFIER = {
    "id": TARGET_WS_ID,
    "uri": {
        "$mid": 1,
        "fsPath": "c:\\kod\\home_assistant",
        "_sep": 1,
        "external": "file:///c%3A/kod/home_assistant",
        "path": "/C:/kod/home_assistant",
        "scheme": "file"
    }
}

TO_MOVE = [
    '66116a8d-4934-47cc-a94c-745cfe2455b7',
    '6f95005f-5c43-4446-abcd-bb258a38e637',
    '43d92d09-ef46-49d1-996b-cbb1a0969eff',
    '8d1767e5-4fcb-404a-8cf1-d6cf6a502aa1',
    '187d3ed9-f6da-4f0a-9088-30452af78cce',
]

def backup_rows(conn, cids):
    cur = conn.cursor()
    backup = {'timestamp': datetime.now().isoformat(), 'chats': {}}
    for cid in cids:
        chat_backup = {}
        cur.execute('SELECT workspaceId, isArchived, value FROM composerHeaders WHERE composerId=?', (cid,))
        r = cur.fetchone()
        if r:
            chat_backup['composerHeaders'] = {'workspaceId': r[0], 'isArchived': r[1], 'value': r[2]}
        cur.execute('SELECT value FROM cursorDiskKV WHERE key=?', (f'composerData:{cid}',))
        r = cur.fetchone()
        if r:
            chat_backup['composerData'] = r[0]
        backup['chats'][cid] = chat_backup
    with open(BACKUP_JSON, 'w', encoding='utf-8') as f:
        json.dump(backup, f, indent=2, ensure_ascii=False)
    print(f'Backup saved to {BACKUP_JSON}')

def update_composer_data(value_str):
    data = json.loads(value_str)
    data['workspaceIdentifier'] = TARGET_WS_IDENTIFIER
    # Replace any granskningsverktyget path refs in the JSON
    result = json.dumps(data, ensure_ascii=False)
    result = result.replace('granskningsverktyget\\\\sessionversion', 'home_assistant')
    result = result.replace('granskningsverktyget/sessionversion', 'home_assistant')
    result = result.replace(SOURCE_WS_ID, TARGET_WS_ID)
    return result

def update_header_value(value_str):
    if not value_str:
        return value_str
    result = value_str.replace(SOURCE_WS_ID, TARGET_WS_ID)
    result = result.replace('granskningsverktyget\\\\sessionversion', 'home_assistant')
    result = result.replace('granskningsverktyget/sessionversion', 'home_assistant')
    return result

def migrate_db(conn, cids):
    cur = conn.cursor()
    for cid in cids:
        # Update composerHeaders
        cur.execute('SELECT isArchived, value FROM composerHeaders WHERE composerId=? AND workspaceId=?', (cid, SOURCE_WS_ID))
        r = cur.fetchone()
        if not r:
            print(f'  SKIP {cid}: not found in source workspace')
            continue
        is_archived, header_value = r
        new_header_value = update_header_value(header_value)
        cur.execute(
            'UPDATE composerHeaders SET workspaceId=?, value=? WHERE composerId=?',
            (TARGET_WS_ID, new_header_value, cid)
        )
        print(f'  Updated composerHeaders {cid} (archived={is_archived})')

        # Update composerData
        cur.execute('SELECT value FROM cursorDiskKV WHERE key=?', (f'composerData:{cid}',))
        r = cur.fetchone()
        if r:
            new_data = update_composer_data(r[0])
            cur.execute('UPDATE cursorDiskKV SET value=? WHERE key=?', (new_data, f'composerData:{cid}'))
            print(f'  Updated composerData {cid}')
    conn.commit()

def move_transcripts(cids):
    os.makedirs(TARGET_TRANSCRIPTS, exist_ok=True)
    moved = 0
    for cid in cids:
        src = os.path.join(SOURCE_TRANSCRIPTS, cid)
        dst = os.path.join(TARGET_TRANSCRIPTS, cid)
        if not os.path.isdir(src):
            print(f'  No transcript folder for {cid}')
            continue
        if os.path.isdir(dst):
            print(f'  Transcript {cid} already exists at target, merging...')
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                if os.path.isdir(s):
                    if os.path.isdir(d):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copytree(s, d)
                elif not os.path.exists(d):
                    shutil.copy2(s, d)
            shutil.rmtree(src)
        else:
            shutil.move(src, dst)
        print(f'  Moved transcript {cid}')
        moved += 1
    return moved

def verify(conn, cids):
    cur = conn.cursor()
    print('\n=== Verification ===')
    ok = True
    for cid in cids:
        cur.execute('SELECT workspaceId, isArchived FROM composerHeaders WHERE composerId=?', (cid,))
        r = cur.fetchone()
        if not r:
            print(f'  FAIL {cid}: missing from composerHeaders')
            ok = False
            continue
        ws, arch = r
        status = 'OK' if ws == TARGET_WS_ID else 'FAIL'
        if ws != TARGET_WS_ID:
            ok = False
        print(f'  {status} {cid}: ws={ws} archived={arch}')
        cur.execute('SELECT value FROM cursorDiskKV WHERE key=?', (f'composerData:{cid}',))
        r = cur.fetchone()
        if r:
            d = json.loads(r[0])
            ws_id = d.get('workspaceIdentifier', {}).get('id', '?')
            if ws_id != TARGET_WS_ID:
                print(f'    FAIL composerData workspaceId={ws_id}')
                ok = False
    return ok

def main():
    print('Starting HA chat migration...')
    conn = sqlite3.connect(GLOBAL_DB)
    backup_rows(conn, TO_MOVE)
    print('\nUpdating database...')
    migrate_db(conn, TO_MOVE)
    print('\nMoving agent transcripts...')
    moved = move_transcripts(TO_MOVE)
    ok = verify(conn, TO_MOVE)
    conn.close()
    print(f'\nDone. DB updated: {len(TO_MOVE)} chats, transcripts moved: {moved}, verification: {"PASSED" if ok else "FAILED"}')

if __name__ == '__main__':
    main()
