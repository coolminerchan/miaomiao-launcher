using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace OverFieldLocal
{
    // Original vector seaside illustration: no screenshots, accounts or game assets embedded.
    class SeasideHero : Panel
    {
        public SeasideHero() { DoubleBuffered=true; BackColor=Color.FromArgb(214,239,247); }
        protected override void OnPaint(PaintEventArgs e)
        {
            var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;
            using(var b=new LinearGradientBrush(ClientRectangle,Color.FromArgb(203,233,249),Color.FromArgb(240,251,247),90f))g.FillRectangle(b,ClientRectangle);
            float x=Width*.69f,y=Height*.42f;
            using(var cloud=new SolidBrush(Color.FromArgb(205,255,255,255)))
            {
                g.FillEllipse(cloud,x+10,18,83,27);g.FillEllipse(cloud,x+38,6,59,43);g.FillEllipse(cloud,x+73,22,78,24);
                g.FillEllipse(cloud,x+190,57,86,23);g.FillEllipse(cloud,x+210,43,48,37);
            }
            using(var sea=new SolidBrush(Color.FromArgb(135,208,218)))g.FillRectangle(sea,x-18,Height-42,Width-x+20,42);
            using(var wave=new Pen(Color.FromArgb(215,255,255,255),2))
            {g.DrawBezier(wave,x-2,Height-25,x+70,Height-37,x+138,Height-16,x+235,Height-28);g.DrawLine(wave,x+55,Height-13,x+160,Height-13);}
            using(var ring=new Pen(Color.FromArgb(83,145,195,206),1.5f))g.DrawEllipse(ring,x+10,y-10,150,72);
            PointF[] diamond={new PointF(x+85,y-28),new PointF(x+109,y+3),new PointF(x+85,y+34),new PointF(x+61,y+3)};
            using(var b=new LinearGradientBrush(new RectangleF(x+60,y-28,50,62),Color.FromArgb(71,156,206),Color.FromArgb(149,220,235),45f))g.FillPolygon(b,diamond);
            using(var pen=new Pen(Color.FromArgb(236,255,255,255),2))g.DrawPolygon(pen,diamond);
            using(var leaf=new SolidBrush(Color.FromArgb(124,186,150)))
            {g.FillEllipse(leaf,Width-67,Height-50,24,13);g.FillEllipse(leaf,Width-45,Height-67,19,30);g.FillEllipse(leaf,Width-33,Height-42,25,12);}
            base.OnPaint(e);
        }
    }

    partial class LauncherForm
    {
        Label FitLabel(string text,float size,Color color,FontStyle style=FontStyle.Regular)
        {return new Label{Text=text,Font=Theme.Font(size,style),ForeColor=color,BackColor=Color.Transparent,Dock=DockStyle.Fill,AutoSize=false,AutoEllipsis=true,TextAlign=ContentAlignment.MiddleLeft,Margin=Padding.Empty};}
        TableLayoutPanel Grid(int columns,int rows)
        {return new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=columns,RowCount=rows,Margin=Padding.Empty,Padding=Padding.Empty,BackColor=Color.Transparent};}
        void SpaceButton(ActionButton button,bool last=false)
        {button.Dock=DockStyle.Fill;button.Margin=new Padding(0,4,last?0:16,4);button.Font=Theme.Font(10,FontStyle.Bold);button.MinimumSize=new Size(0,44);}

        void SaveUIPreview(string directory)
        {
            Directory.CreateDirectory(directory);
            badge.Text="界面预览";server.UpdateState(false,"尚未启动 · 独立服务");gateway.UpdateState(false,"等待游戏连接");proxy.UpdateState(false,"本地 UID 与房间管理");
            start.Text=backend.Mode=="host"?"发布局域网服务  →":"启动单机游戏  →";
            profileLabel.Text=backend.Mode=="host"?"联机存档  ·  本地保存 / 独立备份":"单机存档  ·  本地保存 / 独立备份";
            logs.Text="欢迎回到开放空间。\n选择运行模式，设置自己的 UID，然后开始你的世界。\n此预览未连接官服、未启动游戏或服务。";
            PerformLayout();var errors=new List<string>();AuditUI(this,errors);
            string stem=backend.Mode+"-"+ClientSize.Width+"x"+ClientSize.Height;
            using(var bitmap=new Bitmap(Width,Height)){DrawToBitmap(bitmap,new Rectangle(0,0,Width,Height));bitmap.Save(Path.Combine(directory,stem+".png"));}
            File.WriteAllText(Path.Combine(directory,stem+".json"),new JavaScriptSerializer().Serialize(new Dictionary<string,object>{{"mode",backend.Mode},{"page",capturePage != null && capturePage.Visible ? "capture" : "world"},{"size",ClientSize.ToString()},{"layoutErrors",errors},{"checked","Button text fit, interactive sibling overlap, child bounds; no game/service operations"}}));
        }
        void AuditUI(Control parent,List<string> errors)
        {
            var textControls=new List<Control>();
            foreach(Control child in parent.Controls)
            {
                if(child is ActionButton)
                {
                    Size text=TextRenderer.MeasureText(child.Text,child.Font,new Size(10000,1000),TextFormatFlags.SingleLine|TextFormatFlags.NoPadding);
                    if(text.Width>child.Width-24 || text.Height>child.Height-16)errors.Add("Button text clipped: "+child.Text);
                    if(child.Right>parent.ClientSize.Width+1 || child.Bottom>parent.ClientSize.Height+1)errors.Add("Button outside row: "+child.Text);
                }
                if(child is Label || child is Button || child is TextBox || child is ComboBox || child is NumericUpDown)textControls.Add(child);
                AuditUI(child,errors);
            }
            for(int a=0;a<textControls.Count;a++)for(int b=a+1;b<textControls.Count;b++)
                if(textControls[a].Bounds.IntersectsWith(textControls[b].Bounds))errors.Add("Sibling overlap: "+textControls[a].Text+" / "+textControls[b].Text);
        }

        void BuildLayout()
        {
            var shell=Grid(2,1);shell.BackColor=Theme.Bg;
            shell.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,222));shell.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));Controls.Add(shell);
            var sideScroll=new Panel{Dock=DockStyle.Fill,AutoScroll=true,BackColor=Color.FromArgb(222,240,241),Margin=Padding.Empty};shell.Controls.Add(sideScroll,0,0);
            var side=Grid(1,18);side.Dock=DockStyle.Top;side.Height=892;side.Padding=new Padding(20,28,20,24);
            side.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            foreach(int height in new[]{36,22,44,52,30,8,52,30,8,52,30,8,52,30,14,40,26,96})side.RowStyles.Add(new RowStyle(SizeType.Absolute,height));
            sideScroll.Controls.Add(side);
            side.Controls.Add(FitLabel("开放空间",18,Theme.Text,FontStyle.Bold),0,0);
            side.Controls.Add(FitLabel("O V E R F I E L D",8.5f,Theme.Muted),0,1);
            side.Controls.Add(FitLabel("选择你的世界",10,Theme.Muted),0,2);
            SpaceButton(soloMode,true);side.Controls.Add(soloMode,0,3);
            side.Controls.Add(FitLabel("仅本机连接 · 独立单机存档",9,Theme.Muted),0,4);
            SpaceButton(hostMode,true);side.Controls.Add(hostMode,0,6);
            side.Controls.Add(FitLabel("发布局域网服务 · 独立联机存档",9,Theme.Muted),0,7);
            SpaceButton(captureMode,true);side.Controls.Add(captureMode,0,9);
            side.Controls.Add(FitLabel("官方客户端采集账号数据",9,Theme.Muted),0,10);
            SpaceButton(roomsButton,true);side.Controls.Add(roomsButton,0,12);
            side.Controls.Add(FitLabel("查看在线玩家与房间",9,Theme.Muted),0,13);
            side.Controls.Add(FitLabel("LOCAL WORLD",8,Theme.Accent,FontStyle.Bold),0,15);
            side.Controls.Add(FitLabel("以自己的 UID 开始\n数据只保存在本电脑\n请勿公开私人存档",9,Theme.Muted),0,16);

            var scroll=new Panel{Dock=DockStyle.Fill,AutoScroll=true,Margin=Padding.Empty,BackColor=Theme.Bg};shell.Controls.Add(scroll,1,0);mainScroll=scroll;
            var layout=Grid(1,8);layout.Dock=DockStyle.Top;layout.Padding=new Padding(26,24,26,22);layout.Height=970;
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            foreach(int height in new[]{132,88,84,150,112,124,132,34})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,height));
            scroll.Controls.Add(layout);scroll.Resize+=delegate{layout.Height=Math.Max(886,scroll.ClientSize.Height);};

            var hero=new SeasideHero{Dock=DockStyle.Fill,Margin=new Padding(0,0,0,18),Padding=new Padding(24,14,24,16)};
            var heroGrid=Grid(2,3);heroGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,64));heroGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,36));
            foreach(int h in new[]{24,58,28})heroGrid.RowStyles.Add(new RowStyle(SizeType.Absolute,h));hero.Controls.Add(heroGrid);
            heroGrid.Controls.Add(FitLabel("O V E R F I E L D  /  本 地 世 界",8.5f,Theme.Muted,FontStyle.Bold),0,0);
            headline.Text="开放空间";headline.Font=Theme.Font(28,FontStyle.Bold);headline.ForeColor=Theme.Text;headline.Dock=DockStyle.Fill;headline.AutoSize=false;headline.AutoEllipsis=true;headline.BackColor=Color.Transparent;headline.TextAlign=ContentAlignment.MiddleLeft;headline.Margin=Padding.Empty;heroGrid.Controls.Add(headline,0,1);
            subtitle.Font=Theme.Font(9.5f);subtitle.ForeColor=Theme.Muted;subtitle.Dock=DockStyle.Fill;subtitle.AutoSize=false;subtitle.AutoEllipsis=true;subtitle.BackColor=Color.Transparent;subtitle.TextAlign=ContentAlignment.MiddleLeft;subtitle.Margin=Padding.Empty;heroGrid.Controls.Add(subtitle,0,2);
            badge.Text="正在检查";badge.Font=Theme.Font(9,FontStyle.Bold);badge.ForeColor=Theme.Muted;badge.Dock=DockStyle.Fill;badge.AutoEllipsis=true;badge.BackColor=Color.Transparent;badge.TextAlign=ContentAlignment.TopRight;badge.Margin=Padding.Empty;heroGrid.Controls.Add(badge,1,0);
            layout.Controls.Add(hero,0,0);

            var states=Grid(3,1);for(int i=0;i<3;i++)states.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100f/3));states.Margin=new Padding(0,0,0,18);
            server.Margin=gateway.Margin=new Padding(0,0,16,0);proxy.Margin=Padding.Empty;states.Controls.Add(server,0,0);states.Controls.Add(gateway,1,0);states.Controls.Add(proxy,2,0);layout.Controls.Add(states,0,1);
            var actions=Grid(3,1);foreach(float w in new[]{48f,26f,26f})actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,w));actions.Margin=new Padding(0,0,0,18);
            SpaceButton(start);start.Font=Theme.Font(12,FontStyle.Bold);SpaceButton(services);SpaceButton(stop,true);actions.Controls.Add(start,0,0);actions.Controls.Add(services,1,0);actions.Controls.Add(stop,2,0);layout.Controls.Add(actions,0,2);

            var settings=new Surface{Dock=DockStyle.Fill,Padding=new Padding(20,12,20,14),Margin=new Padding(0,0,0,18)};
            var settingRows=Grid(1,3);settingRows.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));foreach(int h in new[]{26,48,44})settingRows.RowStyles.Add(new RowStyle(SizeType.Absolute,h));settings.Controls.Add(settingRows);
            settingRows.Controls.Add(FitLabel("启动设置",10,Theme.Text,FontStyle.Bold),0,0);
            var pathRow=Grid(2,1);pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,138));
            rootPath.Text=String.IsNullOrWhiteSpace(backend.Root)?"单机模式：请选择本地客户端目录":backend.Root;rootPath.ReadOnly=true;rootPath.BorderStyle=BorderStyle.None;rootPath.BackColor=Theme.Panel;rootPath.ForeColor=Theme.Text;rootPath.Font=Theme.Font(10);rootPath.Dock=DockStyle.Fill;rootPath.Margin=new Padding(0,15,16,6);
            SpaceButton(browse,true);browse.Margin=new Padding(0,2,0,2);pathRow.Controls.Add(rootPath,0,0);pathRow.Controls.Add(browse,1,0);settingRows.Controls.Add(pathRow,0,1);
            var uidRow=Grid(4,1);foreach(float w in new[]{56f,178f,92f})uidRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,w));uidRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            uidRow.Controls.Add(FitLabel("UID",9.5f,Theme.Muted),0,0);
            uidBox.Minimum=1;uidBox.Maximum=UInt32.MaxValue;uidBox.Value=backend.Uid;uidBox.Dock=DockStyle.Fill;uidBox.Font=Theme.Font(11);uidBox.BackColor=Theme.Panel;uidBox.ForeColor=Theme.Text;uidBox.Margin=new Padding(0,9,24,5);uidRow.Controls.Add(uidBox,1,0);
            uidRow.Controls.Add(FitLabel("服务地址",9.5f,Theme.Muted),2,0);
            hostBox.DropDownStyle=ComboBoxStyle.DropDownList;hostBox.Dock=DockStyle.Fill;hostBox.Font=Theme.Font(10);hostBox.BackColor=Theme.Panel;hostBox.ForeColor=Theme.Text;hostBox.Margin=new Padding(0,9,0,5);uidRow.Controls.Add(hostBox,3,0);settingRows.Controls.Add(uidRow,0,2);layout.Controls.Add(settings,0,3);

            var dataPanel=new Surface{Dock=DockStyle.Fill,Padding=new Padding(20,12,20,14),Margin=new Padding(0,0,0,18)};
            var dataRows=Grid(1,2);dataRows.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));dataRows.RowStyles.Add(new RowStyle(SizeType.Absolute,28));dataRows.RowStyles.Add(new RowStyle(SizeType.Percent,100));dataPanel.Controls.Add(dataRows);
            profileLabel.Dock=DockStyle.Fill;profileLabel.AutoEllipsis=true;profileLabel.Font=Theme.Font(9);profileLabel.ForeColor=Theme.Muted;profileLabel.TextAlign=ContentAlignment.MiddleLeft;profileLabel.Margin=Padding.Empty;dataRows.Controls.Add(profileLabel,0,0);
            var dataActions=Grid(4,1);for(int i=0;i<4;i++)dataActions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,25));int index=0;foreach(var b in new[]{importData,backupData,openData,firewall}){SpaceButton(b,index==3);dataActions.Controls.Add(b,index++,0);}dataRows.Controls.Add(dataActions,0,1);layout.Controls.Add(dataPanel,0,5);

            capturePage=new Surface{Dock=DockStyle.Fill,Padding=new Padding(24,18,24,20),Margin=Padding.Empty,Visible=false};
            var captureRows=Grid(1,7);captureRows.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            foreach(int h in new[]{34,28,58,66,10,124,126})captureRows.RowStyles.Add(new RowStyle(SizeType.Absolute,h));capturePage.Controls.Add(captureRows);
            captureRows.Controls.Add(FitLabel("公服账号采集",11,Theme.Text,FontStyle.Bold),0,0);
            captureRows.Controls.Add(FitLabel("公服启动器路径（仅公服，与私服目录独立）",9.5f,Theme.Muted),0,1);
            var officialRow=Grid(2,1);officialRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));officialRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,146));
            officialLauncherPath.Text=String.IsNullOrWhiteSpace(backend.OfficialLauncherPath)?"请选择公服启动器或未修改的原版客户端 EXE":backend.OfficialLauncherPath;
            officialLauncherPath.ReadOnly=true;officialLauncherPath.BorderStyle=BorderStyle.FixedSingle;officialLauncherPath.BackColor=Theme.Panel;officialLauncherPath.ForeColor=Theme.Text;officialLauncherPath.Font=Theme.Font(9.5f);officialLauncherPath.Dock=DockStyle.Fill;officialLauncherPath.Margin=new Padding(0,12,16,10);
            SpaceButton(officialBrowse,true);officialRow.Controls.Add(officialLauncherPath,0,0);officialRow.Controls.Add(officialBrowse,1,0);captureRows.Controls.Add(officialRow,0,2);
            captureHint.Dock=DockStyle.Fill;captureHint.AutoSize=false;captureHint.AutoEllipsis=true;captureHint.Font=Theme.Font(9);captureHint.ForeColor=Theme.Muted;captureHint.TextAlign=ContentAlignment.TopLeft;captureHint.Margin=Padding.Empty;
            captureHint.Text="开始采集会先确认抓包就绪，再自动打开这里配置的公服启动器。使用自己的账号正常登录，采集数据只写入本机账号库。";
            captureRows.Controls.Add(captureHint,0,3);
            var captureActions=Grid(1,2);for(int i=0;i<2;i++)captureActions.RowStyles.Add(new RowStyle(SizeType.Percent,50));
            SpaceButton(captureStart);SpaceButton(captureStop,true);
            
            captureActions.Controls.Add(captureStart,0,0);captureActions.Controls.Add(captureStop,0,1);
            captureRows.Controls.Add(captureActions,0,5);
            captureSteps.Dock=DockStyle.Fill;captureSteps.AutoSize=false;captureSteps.Font=Theme.Font(9);captureSteps.ForeColor=Theme.Muted;captureSteps.TextAlign=ContentAlignment.TopLeft;captureSteps.TextAlign=ContentAlignment.TopLeft;captureSteps.Margin=Padding.Empty;
            captureSteps.Text="1. 单独选择公服启动器路径，不要选择 profiles 中的私服副本\n2. 点「开始采集」，抓包就绪后会自动打开公服，正常登录并进入场景\n3. 依次打开角色、背包、装备、宠物、邮件、家园等界面，等加载完成\n4. 回到启动器点「结束采集」，核对 UID 与冲突提示后确认入库\n5. 采集需要管理员权限，请先停止私服服务和转发工具";
            captureRows.Controls.Add(captureSteps,0,6);
            scroll.Controls.Add(capturePage);

            var logPanel=new Surface{Dock=DockStyle.Fill,Margin=Padding.Empty,Padding=new Padding(20,12,20,14)};
            var logRows=Grid(1,2);logRows.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));logRows.RowStyles.Add(new RowStyle(SizeType.Absolute,30));logRows.RowStyles.Add(new RowStyle(SizeType.Percent,100));logPanel.Controls.Add(logRows);
            var logHead=Grid(2,1);logHead.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));logHead.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,160));logHead.Controls.Add(FitLabel("运行记录",10,Theme.Text,FontStyle.Bold),0,0);
            var openLogs=new LinkLabel{Text="打开日志文件夹",LinkColor=Theme.Muted,ActiveLinkColor=Theme.Accent,VisitedLinkColor=Theme.Muted,Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleRight,AutoSize=false};openLogs.LinkClicked+=delegate{OpenFolder(Path.Combine(backend.ProfilePath,"logs"));};logHead.Controls.Add(openLogs,1,0);logRows.Controls.Add(logHead,0,0);
            logs.Dock=DockStyle.Fill;logs.ReadOnly=true;logs.BackColor=Theme.Panel;logs.ForeColor=Theme.Muted;logs.BorderStyle=BorderStyle.None;logs.Font=Theme.Font(9);logs.DetectUrls=false;logs.ScrollBars=RichTextBoxScrollBars.Vertical;logs.Margin=new Padding(0,4,0,0);logRows.Controls.Add(logs,0,1);layout.Controls.Add(logPanel,0,6);
            footer.Text="游戏与服务独立运行  ·  单机 / 联机存档分开保存";footer.ForeColor=Theme.Muted;footer.Font=Theme.Font(8.5f);footer.Dock=DockStyle.Fill;footer.AutoEllipsis=true;footer.TextAlign=ContentAlignment.BottomLeft;footer.Margin=Padding.Empty;layout.Controls.Add(footer,0,7);
        }
    }
}
