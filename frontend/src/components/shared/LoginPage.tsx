"use client";

import { BookOpen, ShieldCheck, ClipboardCheck, Paperclip, Database } from "lucide-react";
import { FormEvent } from "react";
import { cardClass } from "../shared/utils";
import { statusText } from "../constants";

export type LoginProps = {
  username: string;
  password: string;
  error: string;
  onUsernameChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
};

export function LoginPage({ username, password, error, onUsernameChange, onPasswordChange, onSubmit }: LoginProps) {
  return (
    <main className="min-h-screen bg-surface px-6 py-10">
      <section className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <div className={cardClass("flex min-h-[520px] flex-col justify-between p-8")}>
          <div>
            <div className="mb-8 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-md bg-brand text-white">
                <BookOpen size={24} />
              </div>
              <div>
                <h1 className="text-2xl font-semibold">智能电子实验笔记系统</h1>
                <p className="mt-1 text-sm text-muted">知识图谱、RAG 与科研过程管理一体化工作台</p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {[
                { icon: ShieldCheck, title: "项目隔离", text: "敏感项目显式授权，普通成员只看授权项目。" },
                { icon: ClipboardCheck, title: "审批留痕", text: "笔记提交、审核、退回和版本记录可追溯。" },
                { icon: Paperclip, title: "附件归档", text: "文件上传、下载和审计记录已接入。" },
                { icon: Database, title: "本地 RAG", text: "审核资料本地向量化，并由 DeepSeek 生成可追溯回答。" },
              ].map((item) => (
                <div key={item.title} className="rounded-md border border-border p-4">
                  <item.icon className="mb-3 text-brand" size={22} />
                  <h2 className="font-medium">{item.title}</h2>
                  <p className="mt-2 text-sm leading-6 text-muted">{item.text}</p>
                </div>
              ))}
            </div>
          </div>
          <p className="text-sm text-muted">默认管理员：admin / admin123。首次正式部署后请立即修改密码。</p>
        </div>
        <form onSubmit={onSubmit} className={cardClass("p-6")}>
          <h2 className="text-xl font-semibold">登录</h2>
          <label className="mt-6 block text-sm font-medium">
            账号
            <input
              className="mt-2 w-full rounded-md border border-border px-3 py-2 outline-none focus:border-brand"
              value={username}
              onChange={(e) => onUsernameChange(e.target.value)}
            />
          </label>
          <label className="mt-4 block text-sm font-medium">
            密码
            <input
              className="mt-2 w-full rounded-md border border-border px-3 py-2 outline-none focus:border-brand"
              type="password"
              value={password}
              onChange={(e) => onPasswordChange(e.target.value)}
            />
          </label>
          {error && <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <button className="mt-6 w-full rounded-md bg-brand px-4 py-2 font-medium text-white hover:bg-[#145c73]">登录工作台</button>
        </form>
      </section>
    </main>
  );
}
