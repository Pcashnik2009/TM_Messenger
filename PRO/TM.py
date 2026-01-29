import customtkinter as ctk

from tkinter import messagebox, Toplevel

import firebase_admin

from firebase_admin import credentials, db

import threading

import os

import sys

import base64

import sounddevice as sd

from scipy.io.wavfile import write

import numpy as np

import io

import json

import time

from datetime import datetime



# --- Настройки ---

ctk.set_appearance_mode("dark")

ctk.set_default_color_theme("blue")

SESSION_FILE = "session.json"



# --- Инициализация Firebase ---

if not os.path.exists("key.json"):

    print("Ошибка: key.json не найден!"); sys.exit()



try:

    if not firebase_admin._apps:

        cred = credentials.Certificate("key.json")

        firebase_admin.initialize_app(cred, {'databaseURL': 'https://tm-chat-87803-default-rtdb.firebaseio.com/'})

except Exception as e:

    print(f"Ошибка: {e}"); sys.exit()



class TMMessenger(ctk.CTk):

    def __init__(self):

        super().__init__()

        self.title("TM Messenger Pro")

        self.geometry("1000x700")

       

        self.current_user = None

        self.active_room_path = None

        self.active_chat_id = None

        self.is_group = False

        self.last_msg_count = -1

        self.voice_map = {}

        self.running = True

       

        self.check_auto_login()



    # --- Авторизация (с сохранением сессии) ---

    def check_auto_login(self):

        if os.path.exists(SESSION_FILE):

            try:

                with open(SESSION_FILE, "r") as f:

                    data = json.load(f)

                    threading.Thread(target=self.silent_login, args=(data["n"], data["p"]), daemon=True).start()

                    self.show_loading(); return

            except: pass

        self.show_auth()



    def show_loading(self):

        for w in self.winfo_children(): w.destroy()

        ctk.CTkLabel(self, text="Загрузка TM Messenger...", font=("Arial", 20)).place(relx=0.5, rely=0.5, anchor="center")



    def silent_login(self, n, p):

        try:

            u = db.reference(f'users/{n}').get()

            if u and u.get('password') == p:

                self.current_user = n

                self.after(0, self.main_window)

                threading.Thread(target=self.background_worker, daemon=True).start()

            else: self.after(0, self.show_auth)

        except: self.after(0, self.show_auth)



    def show_auth(self):

        for w in self.winfo_children(): w.destroy()

        f = ctk.CTkFrame(self, fg_color="transparent"); f.place(relx=0.5, rely=0.5, anchor="center")

        t = ctk.CTkTabview(f, width=300); t.pack()

        t.add("Вход"); t.add("Регистрация")

        self.l_n = ctk.CTkEntry(t.tab("Вход"), placeholder_text="Ник"); self.l_n.pack(pady=5)

        self.l_p = ctk.CTkEntry(t.tab("Вход"), placeholder_text="Пароль", show="*"); self.l_p.pack(pady=5)

        ctk.CTkButton(t.tab("Вход"), text="Войти", command=self.login).pack(pady=10)

        self.r_n = ctk.CTkEntry(t.tab("Регистрация"), placeholder_text="Ник"); self.r_n.pack(pady=5)

        self.r_p = ctk.CTkEntry(t.tab("Регистрация"), placeholder_text="Пароль", show="*"); self.r_p.pack(pady=5)

        ctk.CTkButton(t.tab("Регистрация"), text="Создать", command=self.register).pack(pady=10)



    def login(self):

        n, p = self.l_n.get().strip(), self.l_p.get().strip()

        threading.Thread(target=self.silent_login, args=(n, p), daemon=True).start()

        with open(SESSION_FILE, "w") as f: json.dump({"n": n, "p": p}, f)



    def register(self):

        n, p = self.r_n.get().strip(), self.r_p.get().strip()

        if n and p:

            db.reference(f'users/{n}').set({'password': p, 'status': 'Офлайн', 'display_name': n})

            messagebox.showinfo("Успех", "Аккаунт создан!")



    # --- Главное окно ---

    def main_window(self):

        for w in self.winfo_children(): w.destroy()

        self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)

       

        # Сайдбар (слева)

        self.side = ctk.CTkFrame(self, width=300, corner_radius=0)

        self.side.grid(row=0, column=0, sticky="nsew")

       

        # Инфо о себе

        self.me_f = ctk.CTkFrame(self.side, fg_color="transparent")

        self.me_f.pack(pady=10, fill="x", padx=10)

        self.me_lbl = ctk.CTkLabel(self.me_f, text=f"👤 {self.current_user}", font=("Arial", 16, "bold"))

        self.me_lbl.pack(side="left")

        ctk.CTkButton(self.me_f, text="⚙", width=30, command=self.open_my_profile).pack(side="right")

       

        self.search_e = ctk.CTkEntry(self.side, placeholder_text="Поиск ника..."); self.search_e.pack(padx=10, fill="x")

        self.search_e.bind("<Return>", lambda e: self.search_global())



        self.tabs = ctk.CTkTabview(self.side); self.tabs.pack(fill="both", expand=True, padx=5)

        self.tabs.add("Друзья"); self.tabs.add("Группы")

        self.friends_f = ctk.CTkScrollableFrame(self.tabs.tab("Друзья"), fg_color="transparent"); self.friends_f.pack(fill="both", expand=True)

        self.groups_f = ctk.CTkScrollableFrame(self.tabs.tab("Группы"), fg_color="transparent"); self.groups_f.pack(fill="both", expand=True)



        ctk.CTkButton(self.side, text="+ Группа", command=self.create_group_dialog).pack(pady=5, padx=10, fill="x")

        ctk.CTkButton(self.side, text="Выйти", fg_color="#d9534f", command=self.logout).pack(pady=10, padx=10, fill="x")



        # Окно чата (справа)

        self.chat_area = ctk.CTkFrame(self, fg_color="#141414", corner_radius=0)

        self.chat_area.grid(row=0, column=1, sticky="nsew")

       

        self.header = ctk.CTkFrame(self.chat_area, fg_color="#1a1a1a", height=50); self.header.pack(fill="x")

        self.c_title = ctk.CTkLabel(self.header, text="Выберите чат", font=("Arial", 16)); self.c_title.pack(side="left", padx=20)

        self.invite_btn = ctk.CTkButton(self.header, text="Пригласить", width=100, command=self.invite_to_group)

        self.manage_btn = ctk.CTkButton(self.header, text="Настроить", width=100, command=self.open_manage_window)



        self.txt = ctk.CTkTextbox(self.chat_area, state="disabled", wrap="word")

        self.txt.pack(fill="both", expand=True, padx=20, pady=5)

        self.txt.bind("<Button-1>", self.on_click_msg); self.txt.tag_config("link", foreground="#3498db")



        inp_f = ctk.CTkFrame(self.chat_area, fg_color="transparent"); inp_f.pack(fill="x", padx=20, pady=20)

        self.v_btn = ctk.CTkButton(inp_f, text="🎤", width=40, fg_color="#2c3e50")

        self.v_btn.pack(side="left", padx=5)

        self.v_btn.bind("<ButtonPress-1>", self.start_rec); self.v_btn.bind("<ButtonRelease-1>", self.stop_rec)

       

        self.msg_e = ctk.CTkEntry(inp_f, placeholder_text="Сообщение..."); self.msg_e.pack(side="left", fill="x", expand=True, padx=5)

        self.msg_e.bind("<Return>", lambda e: self.send_t())

        ctk.CTkButton(inp_f, text="➡", width=50, command=self.send_t).pack(side="right")

       

        self.protocol("WM_DELETE_WINDOW", self.on_close)



    # --- Настройка профиля ---

    def open_my_profile(self):

        win = Toplevel(self); win.title("Мой профиль"); win.geometry("300x250"); win.configure(bg="#1a1a1a")

        u_info = db.reference(f'users/{self.current_user}').get()

       

        ctk.CTkLabel(win, text="Изменить имя профиля:", font=("Arial", 14)).pack(pady=10)

        name_e = ctk.CTkEntry(win); name_e.insert(0, u_info.get('display_name', self.current_user)); name_e.pack(pady=10)

       

        def save():

            new_name = name_e.get().strip()

            if new_name:

                db.reference(f'users/{self.current_user}/display_name').set(new_name)

                self.me_lbl.configure(text=f"👤 {new_name}")

                win.destroy()

        ctk.CTkButton(win, text="Сохранить", fg_color="#2ecc71", command=save).pack(pady=10)



    # --- Настройка группы ---

    def open_manage_window(self):

        if not self.is_group: return

        gid = self.active_chat_id

        info = db.reference(f'groups/{gid}').get()

        if info.get('owner') != self.current_user:

            messagebox.showwarning("Доступ", "Только админ может менять название"); return



        win = Toplevel(self); win.title("Управление группой"); win.geometry("350x400"); win.configure(bg="#1a1a1a")

        ctk.CTkLabel(win, text="Новое название группы:").pack(pady=10)

        gn_e = ctk.CTkEntry(win); gn_e.insert(0, info.get('name', '')); gn_e.pack(pady=10)

       

        def update_gn():

            new_gn = gn_e.get().strip()

            if new_gn:

                db.reference(f'groups/{gid}/name').set(new_gn)

                self.c_title.configure(text=f"Группа: {new_gn}")

                messagebox.showinfo("Успех", "Название обновлено")



        ctk.CTkButton(win, text="Сменить название", command=update_gn).pack(pady=5)

       

        # Список участников для кика

        frame = ctk.CTkScrollableFrame(win, height=150); frame.pack(fill="x", padx=10, pady=10)

        members = info.get('members', {})

        for m in members.keys():

            m_f = ctk.CTkFrame(frame); m_f.pack(fill="x", pady=2)

            ctk.CTkLabel(m_f, text=m).pack(side="left", padx=5)

            if m != self.current_user:

                ctk.CTkButton(m_f, text="Кик", width=50, fg_color="red", command=lambda x=m: self.kick_member(gid, x, win)).pack(side="right")



    def kick_member(self, gid, member, win):

        db.reference(f'groups/{gid}/members/{member}').delete()

        db.reference(f'users/{member}/groups/{gid}').delete()

        win.destroy(); self.open_manage_window()



    # --- Фоновое обновление ---

    def background_worker(self):

        while self.running:

            try:

                if self.current_user:

                    db.reference(f'users/{self.current_user}/status').set("В сети")

                self.after(0, self.draw_lists)

                if self.active_room_path:

                    data = db.reference(f'messages/{self.active_room_path}').get()

                    count = len(data) if data else 0

                    if count != self.last_msg_count:

                        self.last_msg_count = count

                        self.after(0, lambda: self.render_messages(data))

                time.sleep(2)

            except: time.sleep(5)



    def draw_lists(self):

        try:

            # Друзья

            friends = db.reference(f'users/{self.current_user}/contacts').get()

            f_db_names = set(friends.keys()) if friends else set()

            for w in self.friends_f.winfo_children():

                if getattr(w, "_id", None) not in f_db_names: w.destroy()



            for n in f_db_names:

                fdata = db.reference(f'users/{n}').get()

                if not fdata: continue

                disp_name = fdata.get('display_name', n)

                status = fdata.get('status', 'Офлайн')

                status_clr = "#2ecc71" if status == "В сети" else "#95a5a6"

               

                exists = False

                for w in self.friends_f.winfo_children():

                    if getattr(w, "_id", None) == n:

                        w._btn.configure(text=f"👤 {disp_name}", text_color=status_clr)

                        exists = True; break

                if not exists:

                    f = ctk.CTkFrame(self.friends_f, fg_color="transparent"); f.pack(fill="x", pady=1); f._id = n

                    f._btn = ctk.CTkButton(f, text=f"👤 {disp_name}", anchor="w", fg_color="transparent", text_color=status_clr, command=lambda x=n: self.sw_chat(x, False))

                    f._btn.pack(side="left", fill="x", expand=True)

                    ctk.CTkButton(f, text="❌", width=30, fg_color="transparent", command=lambda x=n: self.delete_friend(x)).pack(side="right")



            # Группы

            groups = db.reference(f'users/{self.current_user}/groups').get()

            g_db_ids = set(groups.keys()) if groups else set()

            for w in self.groups_f.winfo_children():

                if getattr(w, "_id", None) not in g_db_ids: w.destroy()



            for gid in g_db_ids:

                info = db.reference(f'groups/{gid}').get()

                if not info: continue

                gname = info.get('name', 'Группа')

               

                exists = False

                for w in self.groups_f.winfo_children():

                    if getattr(w, "_id", None) == gid:

                        w._btn.configure(text=f"👥 {gname}")

                        exists = True; break

                if not exists:

                    f = ctk.CTkFrame(self.groups_f, fg_color="transparent"); f.pack(fill="x", pady=1); f._id = gid

                    f._btn = ctk.CTkButton(f, text=f"👥 {gname}", anchor="w", fg_color="transparent", command=lambda x=gid, n=gname: self.sw_chat(x, True, n))

                    f._btn.pack(side="left", fill="x", expand=True)

                    ctk.CTkButton(f, text="❌", width=30, fg_color="transparent", command=lambda x=gid: self.leave_group(x)).pack(side="right")

        except: pass



    # --- Логика чата и голосовых ---

    def sw_chat(self, target, is_group, name=None):

        self.active_chat_id = target; self.is_group = is_group

        self.manage_btn.pack_forget(); self.invite_btn.pack_forget()

        if not target:

            self.active_room_path = None; self.c_title.configure(text="Выберите чат")

        elif is_group:

            self.active_room_path = f"group_{target}"

            self.invite_btn.pack(side="right", padx=10)

            self.c_title.configure(text=f"Группа: {name}")

            info = db.reference(f'groups/{target}').get()

            if info and info.get('owner') == self.current_user: self.manage_btn.pack(side="right", padx=5)

        else:

            self.active_room_path = "_".join(sorted([self.current_user, target]))

            self.c_title.configure(text=f"Чат: {target}")

        self.last_msg_count = -1

        self.txt.configure(state="normal"); self.txt.delete("0.0", "end"); self.txt.configure(state="disabled")



    def render_messages(self, data):

        self.txt.configure(state="normal"); self.txt.delete("0.0", "end"); self.voice_map.clear()

        if data:

            for k in sorted(data.keys()):

                m = data[k]; s = "Вы" if m['sender'] == self.current_user else m['sender']

                if m.get('type') == 'voice':

                    line = self.txt.index("end-1c").split(".")[0]

                    self.txt.insert("end", f"[{m['time']}] {s}: "); self.txt.insert("end", "▶ Голосовое сообщение", "link")

                    self.txt.insert("end", "\n\n"); self.voice_map[line] = k

                else:

                    self.txt.insert("end", f"[{m.get('time','00:00')}] {s}: {m['content']}\n\n")

        self.txt.configure(state="disabled"); self.txt.see("end")



    def send_t(self):

        v = self.msg_e.get().strip()

        if v and self.active_room_path:

            msg = {'sender': self.current_user, 'content': v, 'type': 'text', 'time': datetime.now().strftime("%H:%M")}

            threading.Thread(target=lambda: db.reference(f'messages/{self.active_room_path}').push(msg), daemon=True).start()

            self.msg_e.delete(0, 'end')



    def start_rec(self, e):

        if not self.active_room_path: return

        self.is_recording = True; self.recording_data = []

        self.v_btn.configure(fg_color="#e74c3c")

        self.stream = sd.InputStream(samplerate=16000, channels=1, callback=lambda i,f,t,s: self.recording_data.append(i.copy()))

        self.stream.start()



    def stop_rec(self, e):

        if not hasattr(self, 'is_recording') or not self.is_recording: return

        self.is_recording = False; self.v_btn.configure(fg_color="#2c3e50")

        try:

            self.stream.stop(); self.stream.close()

            threading.Thread(target=self.upload_v, daemon=True).start()

        except: pass



    def upload_v(self):

        try:

            audio = np.concatenate(self.recording_data, axis=0)

            b_io = io.BytesIO(); write(b_io, 16000, (audio * 32767).astype(np.int16))

            db.reference(f'messages/{self.active_room_path}').push({

                'sender': self.current_user, 'content': base64.b64encode(b_io.getvalue()).decode('utf-8'),

                'type': 'voice', 'time': datetime.now().strftime("%H:%M")

            })

        except: pass



    def on_click_msg(self, event):

        idx = self.txt.index(f"@{event.x},{event.y} linestart").split(".")[0]

        if idx in self.voice_map:

            m_id = self.voice_map[idx]

            threading.Thread(target=self.play_v, args=(m_id,), daemon=True).start()



    def play_v(self, m_id):

        try:

            d = db.reference(f'messages/{self.active_room_path}/{m_id}/content').get()

            if d:

                import scipy.io.wavfile as wav

                fs, data = wav.read(io.BytesIO(base64.b64decode(d)))

                sd.play(data, fs)

        except: pass



    def search_global(self):

        q = self.search_e.get().strip()

        if not q: return

        u = db.reference(f'users/{q}').get()

        if u and q != self.current_user:

            db.reference(f'users/{self.current_user}/contacts/{q}').set(True)

            db.reference(f'users/{q}/contacts/{self.current_user}').set(True)

            messagebox.showinfo("Успех", f"{q} добавлен в друзья")

        else:

            messagebox.showinfo("Инфо", "Пользователь не найден")



    def create_group_dialog(self):

        n = ctk.CTkInputDialog(text="Имя группы:", title="Создать").get_input()

        if n:

            res = db.reference('groups').push({'name': n, 'owner': self.current_user, 'members': {self.current_user: True}})

            db.reference(f'users/{self.current_user}/groups/{res.key}').set(True)



    def invite_to_group(self):

        if self.is_group:

            f = ctk.CTkInputDialog(text="Ник друга:", title="Пригласить").get_input()

            if f:

                db.reference(f'groups/{self.active_chat_id}/members/{f}').set(True)

                db.reference(f'users/{f}/groups/{self.active_chat_id}').set(True)



    def delete_friend(self, name):

        if messagebox.askyesno("Удаление", f"Удалить {name}?"):

            db.reference(f'users/{self.current_user}/contacts/{name}').delete()



    def leave_group(self, gid):

        if messagebox.askyesno("Выход", "Выйти из группы?"):

            db.reference(f'users/{self.current_user}/groups/{gid}').delete()



    def logout(self):

        if os.path.exists(SESSION_FILE): os.remove(SESSION_FILE)

        self.on_close()



    def on_close(self):

        self.running = False

        try: db.reference(f'users/{self.current_user}/status').set("Офлайн")

        except: pass

        self.destroy()



if __name__ == "__main__": TMMessenger().mainloop()
