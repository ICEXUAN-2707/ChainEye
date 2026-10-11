import socket
import unittest

from tools.smoke_local import require_free_port


class LocalSmokeSafety(unittest.TestCase):
    def test_occupied_port_is_rejected_before_process_start(self):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1',0));listener.listen()
            port=listener.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError,str(port)):
                require_free_port(port)


if __name__=='__main__':unittest.main()
