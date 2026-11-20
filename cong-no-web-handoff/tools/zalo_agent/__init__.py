"""ZALO-AGENT-01: tiến trình nền ở máy có Zalo, đọc kho live-sync theo revision và đẩy lên hao."""
import logging

logging.getLogger("zalo_agent").addHandler(logging.NullHandler())   # thư viện không in ra stderr khi chưa cấu hình log
