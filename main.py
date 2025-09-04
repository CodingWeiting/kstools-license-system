import os
  import gradio as gr
  from fastapi import FastAPI, HTTPException
  from supabase import create_client, Client
  from datetime import datetime
  import logging

  # 設定日誌
  logging.basicConfig(level=logging.INFO)
  logger = logging.getLogger(__name__)

  # Supabase 連接
  SUPABASE_URL = os.environ.get("SUPABASE_URL")
  SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")

  if not SUPABASE_URL or not SUPABASE_KEY:
      logger.error("請設定 SUPABASE_URL 和 SUPABASE_ANON_KEY 環境變數")
      # 在開發環境中可以暫時使用預設值
      SUPABASE_URL = "https://placeholder.supabase.co"
      SUPABASE_KEY = "placeholder_key"

  try:
      supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
  except Exception as e:
      logger.error(f"Supabase 連接失敗: {e}")
      supabase = None

  app = FastAPI(title="KSTools 授權系統")

  # === API 端點 ===
  @app.post("/api/request-license")
  async def request_license(request: dict):
      """處理授權申請"""
      if not supabase:
          raise HTTPException(status_code=500, detail="資料庫連接失敗")

      try:
          email = request.get("email", "").strip().lower()
          machine_id = request.get("machine_id", "").strip()
          computer_name = request.get("computer_name", "").strip()

          logger.info(f"授權申請: {email} from {computer_name}")

          # 檢查郵箱格式
          if not email.endswith("@kaohsin.com.tw"):
              raise HTTPException(status_code=400, detail="僅限公司郵箱")

          # 檢查該郵箱是否在授權清單中
          auth_result = supabase.table("authorized_emails")\
              .select("*")\
              .eq("email", email)\
              .eq("status", "Active")\
              .execute()

          if not auth_result.data:
              raise HTTPException(status_code=403, detail="此郵箱未獲授權，請聯絡 IT
  部門申請")

          # 檢查是否已有授權記錄
          existing = supabase.table("licenses").select("*").eq("email",
  email).execute()

          if existing.data:
              existing_license = existing.data[0]

              # 檢查是否為相同電腦
              if existing_license["machine_id"] != machine_id:
                  raise HTTPException(
                      status_code=403,
                      detail=f"此郵箱已授權給其他電腦
  ({existing_license.get('computer_name', '未知')})"
                  )

              # 相同電腦，更新最後使用時間
              supabase.table("licenses").update({
                  "last_used": datetime.now().isoformat()
              }).eq("email", email).execute()

              return {"authorized": True, "message": "授權驗證成功"}

          # 新的授權，建立記錄
          license_data = {
              "email": email,
              "machine_id": machine_id,
              "computer_name": computer_name,
              "status": "Active",
              "authorized_at": datetime.now().isoformat(),
              "last_used": datetime.now().isoformat()
          }

          supabase.table("licenses").insert(license_data).execute()
          logger.info(f"新授權建立: {email} -> {computer_name}")

          return {"authorized": True, "message": "授權成功"}

      except HTTPException:
          raise
      except Exception as e:
          logger.error(f"授權申請錯誤: {str(e)}")
          raise HTTPException(status_code=500, detail="系統錯誤")

  # === Gradio 管理介面函數 ===
  def add_license(email):
      """新增郵箱授權"""
      if not supabase:
          return "❌ 資料庫連接失敗", get_users_list()

      try:
          if not email or not email.strip():
              return "❌ 請輸入郵箱", get_users_list()

          email = email.strip().lower()

          if not email.endswith("@kaohsin.com.tw"):
              return "❌ 請輸入公司郵箱", get_users_list()

          # 檢查是否已存在
          existing = supabase.table("authorized_emails").select("*").eq("email",
  email).execute()

          if existing.data:
              return "❌ 該郵箱已在授權清單中", get_users_list()

          # 新增授權
          supabase.table("authorized_emails").insert({
              "email": email,
              "status": "Active",
              "created_at": datetime.now().isoformat()
          }).execute()

          return f"✅ 已新增 {email} 到授權清單", get_users_list()

      except Exception as e:
          return f"❌ 新增失敗: {str(e)}", get_users_list()

  def revoke_license(email):
      """撤銷授權"""
      if not supabase:
          return "❌ 資料庫連接失敗", get_users_list()

      try:
          if not email or not email.strip():
              return "❌ 請輸入郵箱", get_users_list()

          email = email.strip().lower()

          # 撤銷授權清單中的記錄
          supabase.table("authorized_emails")\
              .update({"status": "Revoked"})\
              .eq("email", email)\
              .execute()

          # 撤銷實際授權記錄
          supabase.table("licenses")\
              .update({"status": "Revoked"})\
              .eq("email", email)\
              .execute()

          return f"✅ 已撤銷 {email} 的授權", get_users_list()

      except Exception as e:
          return f"❌ 撤銷失敗: {str(e)}", get_users_list()

  def get_users_list():
      """取得使用者列表"""
      if not supabase:
          return [["資料庫連接失敗", "", "", "", ""]]

      try:
          result = supabase.table("licenses")\
              .select("*")\
              .eq("status", "Active")\
              .order("authorized_at", desc=True)\
              .execute()

          if not result.data:
              return [["目前無授權使用者", "", "", "", ""]]

          users_data = []
          for license in result.data:
              auth_time = license["authorized_at"][:16].replace("T", " ")
              last_used = "從未使用"
              if license.get("last_used"):
                  last_used = license["last_used"][:16].replace("T", " ")

              users_data.append([
                  license["email"],
                  license.get("computer_name", "未知"),
                  auth_time,
                  last_used,
                  "🟢 使用中"
              ])

          return users_data

      except Exception as e:
          return [["錯誤", str(e), "", "", ""]]

  # === 建立 Gradio 介面 ===
  with gr.Blocks(title="KSTools 管理", theme=gr.themes.Soft()) as demo:
      gr.Markdown("# 🔧 KSTools 授權管理")

      with gr.Row():
          with gr.Column(scale=2):
              gr.Markdown("## 📧 授權管理")

              with gr.Group():
                  gr.Markdown("### ➕ 新增授權")
                  new_email = gr.Textbox(
                      label="員工郵箱",
                      placeholder="employee@kaohsin.com.tw"
                  )
                  add_btn = gr.Button("新增授權", variant="primary")
                  add_result = gr.Textbox(label="", lines=1, show_label=False)

              with gr.Group():
                  gr.Markdown("### ❌ 撤銷授權")
                  revoke_email = gr.Textbox(
                      label="員工郵箱",
                      placeholder="employee@kaohsin.com.tw"
                  )
                  revoke_btn = gr.Button("撤銷授權", variant="stop")
                  revoke_result = gr.Textbox(label="", lines=1, show_label=False)

          with gr.Column(scale=3):
              gr.Markdown("## 👥 授權清單")
              refresh_btn = gr.Button("🔄 重新整理")
              users_table = gr.Dataframe(
                  headers=["郵箱", "電腦名稱", "授權時間", "最後使用", "狀態"],
                  label="",
                  height=400
              )

      # 綁定事件
      add_btn.click(add_license, inputs=[new_email], outputs=[add_result,
  users_table])
      revoke_btn.click(revoke_license, inputs=[revoke_email], outputs=[revoke_result,
   users_table])
      refresh_btn.click(get_users_list, outputs=[users_table])

      # 頁面載入時自動載入使用者列表
      demo.load(get_users_list, outputs=[users_table])

  # 掛載到 FastAPI
  app = gr.mount_gradio_app(app, demo, path="/")

  if __name__ == "__main__":
      import uvicorn
      uvicorn.run(app, host="0.0.0.0", port=7860)
