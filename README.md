# ntd-claude-usage

Gom số liệu sử dụng Claude Code từ **nhiều máy** về một repo, mỗi máy tự đẩy dữ liệu của mình lên
hằng ngày. Không cần cài gì ngoài `python 3` + `git`.

## Repo có gì

```
install.bat               cài một chạm trên Windows: kiểm tra máy, tải repo, đăng ký chạy hằng ngày
tools/claude_usage.py     script chạy trên từng máy
tools/install-task.ps1    đăng ký chạy tự động trên Windows
pricing.json              bảng giá USD/1M token (sửa ở đây khi Anthropic đổi giá)
data/<máy>/<tháng>.csv    dữ liệu thô — mỗi máy chỉ ghi thư mục của chính nó
SUMMARY.md                báo cáo, script tự sinh lại sau mỗi lần chạy
```

Mỗi máy chỉ đụng vào `data/<tên máy>/` nên **không bao giờ conflict** với máy khác.

`SUMMARY.md` mở đầu bằng **báo cáo của đúng ngày chạy script** (giờ máy), từng máy một, kèm bảng chi
tiết theo project / session / agent / model của ngày đó. Ngày đó không ai làm gì thì ghi thẳng là
chưa có hoạt động, không lùi sang ngày khác. Máy nào chưa đẩy số liệu thì hiện dấu `-`.

Phần cộng dồn cả kỳ nằm bên dưới, có cột **Ngày dùng** để khỏi đọc nhầm con số cả tháng thành con số
một ngày.

## Cột trong CSV

| Cột | Nghĩa |
|---|---|
| `machine` | Tên máy (mặc định hostname, đổi bằng file `.machine` hoặc `--machine`) |
| `date` | Ngày **giờ địa phương của máy đó** |
| `project` | Thư mục lúc **mở** session. Không lấy `cwd` của từng lượt gọi vì `cwd` trôi theo lệnh `cd` — đã gặp một session mở ở `app445y5_filerecovery` nhưng 619/623 lượt gọi mang `cwd` của project khác |
| `session` | Session id của Claude Code |
| `agent` | `main` cho nhánh chính, hoặc loại subagent (`workflow-subagent`, `Explore`…) lấy từ trường `attributionAgent` |
| `model` | Model id, ví dụ `claude-opus-5` |
| `input` / `output` | Token vào / ra |
| `cache_write_5m` / `cache_write_1h` | Token ghi cache, tách theo TTL vì hai mức giá khác nhau |
| `cache_read` | Token đọc cache — **phần lớn tiền nằm ở đây** |
| `cost_usd` | Tiền quy đổi theo giá API, tính từ đúng 4 cột token ở trên (cộng thêm $0.01/lần web search nếu có) |

Cột `cost_usd` **kiểm lại được** từ 4 cột token nhân giá trong `pricing.json`, nhưng phải chọn đúng
giá cache write theo cột `agent`: **nhánh `main` ghi cache TTL 1h, subagent ghi TTL 5m** — đo trên dữ
liệu thật thì tỉ lệ này là 100%/100%, không lẫn. Hai TTL khác giá nhau ($10 so với $6,25 mỗi triệu
token với Opus 5).

Tính đúng theo `agent`: lệch tổng **$0,000021** trên 95 dòng, chỉ là sai số làm tròn.
Cứ áp giá 1h cho tất cả: lệch **$184** — đủ lớn để tưởng nhầm là script sai.

Một dòng = một tổ hợp (máy, ngày, project, session, agent, model).

## Cài trên một máy mới

Cần đúng 2 thứ: `python 3` và `git`. Không cài thư viện gì thêm.

### Windows — bấm đúp `install.bat`

Tải riêng mỗi file [`install.bat`](install.bat) về rồi bấm đúp. Nó tự làm hết: kiểm tra python/git,
tải repo về `%USERPROFILE%
td-claude-usage`, hỏi tên máy, chạy thử một lần, rồi đăng ký task chạy
hằng ngày.

Thiếu python hay git thì nó dừng lại và in đúng lệnh cần chạy (`winget install ...`) chứ không cài
ngầm sau lưng.

```bat
install.bat check    :: chỉ kiểm tra máy, không đụng gì
```

### macOS / Linux

```bash
git clone https://github.com/tuanla-ntd-vn/ntd-claude-usage.git
cd ntd-claude-usage
echo "MacBook-Huy" > .machine        # tên máy, bỏ qua thì lấy hostname
python3 tools/claude_usage.py        # chạy thử: gom + commit + push
```

Lần chạy đầu tiên quan trọng — vừa kiểm tra script chạy được, vừa để Git hỏi đăng nhập **một lần**
rồi nhớ luôn. Cắm thẳng vào scheduler mà bỏ qua bước này thì task chạy nền treo ở màn hình đăng nhập,
không ai thấy và im lặng không đẩy được gì.

Xong mới dán 2 dòng cron ở mục dưới.

## Chạy tay

```bash
python tools/claude_usage.py --dry-run    # chỉ xem, không ghi gì
python tools/claude_usage.py --no-push    # ghi CSV + SUMMARY.md, tự commit/push lấy
python tools/claude_usage.py              # ghi + commit + push
```

Chạy lại bao nhiêu lần cũng ra kết quả như nhau: mỗi lần quét lại **toàn bộ** transcript rồi ghi đè
dòng tương ứng. Vì vậy hôm nào máy tắt không chạy thì lần chạy sau tự bù, không cần nhớ trạng thái.

Trước khi bật chạy tự động, **push tay một lần** để Git Credential Manager lưu thông tin đăng nhập —
nếu chưa có, task chạy nền sẽ treo ở màn hình đăng nhập mà không ai thấy.

## Chạy tự động

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File tools\install-task.ps1 -Machine "PC-Thien"
```

Đăng ký task `ClaudeUsageDaily`: chạy **23:47 hằng ngày**, cộng thêm **5 phút sau mỗi lần đăng nhập**
để bù ngày hôm trước máy tắt. Bật `StartWhenAvailable` nên máy ngủ qua giờ hẹn thì tỉnh dậy chạy bù.

```powershell
Start-ScheduledTask -TaskName ClaudeUsageDaily      # thử ngay
Get-Content .run.log -Tail 20                       # xem lần chạy gần nhất
powershell -File tools\install-task.ps1 -Uninstall  # gỡ
```

### macOS / Linux

`crontab -e` rồi dán 2 dòng (sửa đường dẫn repo cho đúng máy):

```cron
47 23 * * * cd ~/ntd-claude-usage && /usr/bin/python3 tools/claude_usage.py >> .run.log 2>&1
17 9  * * * cd ~/ntd-claude-usage && /usr/bin/python3 tools/claude_usage.py >> .run.log 2>&1
```

Dòng thứ hai là bản chạy bù buổi sáng, phòng hôm trước máy tắt lúc 23:47. Chạy hai lần vô hại.
Đặt tên máy: `echo "MacBook-Huy" > .machine`.

### Cách khác: hook của Claude Code

Nếu không muốn đụng tới scheduler của hệ điều hành, thêm vào `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command",
                     "command": "python D:\\...\\ntd-claude-usage\\tools\\claude_usage.py" } ] }
    ]
  }
}
```

Mỗi lần mở session Claude Code sẽ đẩy số liệu một lần. Máy nào không mở Claude Code thì cũng không
phát sinh usage, nên cách này phủ gần đủ — chỉ thiếu phần usage của **chính session đang mở**, đến
lần mở sau mới có.

> `/schedule` và cron trong Claude Code **không dùng được cho việc này**: cron trong phiên chỉ sống
> tới khi thoát Claude Code và tự hết hạn sau 7 ngày, còn routine `/schedule` chạy trên cloud nên
> không đọc được file transcript nằm trên máy.

## Số liệu lấy từ đâu, có tin được không

Nguồn là transcript của chính Claude Code: **chỉ `~/.claude/projects/`**, quét đệ quy.

Quét đệ quy là bắt buộc: transcript của **subagent nằm ở thư mục lồng sâu hơn**, không cùng cấp với
session chính:

```
projects/<project>/<session>.jsonl                                   <- nhánh chính
projects/<project>/<session>/subagents/workflows/wf_*/agent-*.jsonl  <- subagent
```

Đo trên máy này: 53 file chính so với **869 file subagent**, phần subagent chiếm **15,4% tổng tiền**
($803 / $5.204). Chỉ quét một cấp là mất sạch phần đó mà không có dấu hiệu gì báo thiếu.

Máy có thể có nhiều profile (`~/.claude-personal`, `~/.claude-work`…) và biến môi trường
`CLAUDE_CONFIG_DIR` có khi đang trỏ sang profile khác — script **cố tình không đụng tới**, chỉ lấy
tài khoản mặc định. Muốn đổi thì sửa hàm `config_dirs()` trong `tools/claude_usage.py`.

Hai điểm đã đối chiếu bằng số, không phải phỏng đoán:

1. **Công thức tính tiền khớp tuyệt đối** với bản ghi `cost-state` do Claude Code tự tính —
   28/28 mục model khớp tới từng chữ số, sau khi tính thêm web search $0.01/lần.
   Cache write ở Claude Code dùng TTL 1h (gấp đôi giá input), không phải 5m.
2. **Một lượt gọi API bị ghi thành nhiều dòng transcript** (mỗi content block một dòng, cùng
   `message.id` + `requestId`, cùng y nguyên khối `usage`). Script gộp lại, đếm một lần.

Vì điểm 2 mà **số ở đây thấp hơn tab `/stats` của Claude Code khoảng 2 lần** — đo bằng
`stats-cache.json` của một profile: ngày 2026-09-08 nó ghi 26.5M token, đếm theo lượt gọi là 12.7M.
Bản gộp mới là bản khớp với sổ tiền của chính Claude Code, nên cột `cost_usd` ở đây đáng tin hơn
con số token của tab Stats.

## Lưu ý

- Đây là **giá API quy đổi**, không phải tiền thật phải trả nếu đang dùng gói thuê bao.
- Ngày tính theo **giờ địa phương của từng máy** — máy khác múi giờ thì ranh giới ngày lệch theo.
- Claude Code tự dọn transcript cũ (mặc định 30 ngày). Script **cộng dồn, không xoá**: dòng đã đẩy
  lên repo vẫn giữ nguyên kể cả khi transcript gốc bị dọn.
- Model chưa có trong `pricing.json` vẫn được ghi nhận token nhưng `cost_usd = 0`, và script in cảnh
  báo tên model đó ra màn hình.
- Script từ chối chạy nếu repo đang có thay đổi chưa commit **ngoài** `data/` và `SUMMARY.md`, để
  không nuốt mất việc đang làm dở.
- **Số session ở đây thấp hơn tab Stats của Claude Code**, và đó là cố ý. App đếm *file transcript*;
  resume một cuộc hội thoại sẽ tạo file mới với session id mới nhưng **chép lại toàn bộ lịch sử cũ**.
  Đo trên máy này: 53 file → 52 session id có usage → **47 session thực sự tiêu tốn gì đó**, 5 cái còn
  lại là bản chép y hệt. Cộng cả 5 vào là tính tiền hai lần.
  Mỗi lượt gọi được gán cho session **có tập lượt gọi nhỏ nhất** trong số các session chứa nó — tức
  session gốc đã thực sự gọi nó; bản resume chỉ nhận phần nó gọi thêm.
#   u s a g e - c l a u d e  
 