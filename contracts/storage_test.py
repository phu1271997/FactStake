# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
try:
    from genlayer.std import bigint
except ImportError:
    pass

class Contract(gl.Contract):
    value: bigint

    def __init__(self, initial_value: bigint):
        self.value = initial_value

    @gl.public.view
    def get_value(self) -> bigint:
        return self.value

    @gl.public.write
    def set_value(self, new_value: bigint):
        self.value = new_value
