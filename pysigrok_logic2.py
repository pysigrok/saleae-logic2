"""PySigrok driver for Saleae Logic 2 exports"""

import csv
import pathlib
import struct

from sigrokdecode.input import Input

from sigrokdecode import cond_matches, OUTPUT_PYTHON

__version__ = "0.0.1"

class Logic2Input(Input):
    name = "logic2"
    desc = "Logic 2 export file format data"
    def __init__(self, filename, initial_state=None, samplecount=None):
        super().__init__()

        if initial_state:
            self.last_sample = 0
            for channel in initial_state:
                self.last_sample |= initial_state[channel] << channel
        else:
            self.last_sample = None

        filename = pathlib.Path(filename)

        if filename.is_dir():
            # Multiple channels
            digital_csv = filename / "digital.csv"
            if not digital_csv.exists():
                raise RuntimeError()
        elif filename.name == "digital.csv":
            digital_csv = filename
        else:
            # One channel
            raise RuntimeError()

        self.one_to_one = True

        self.openfile = digital_csv.open("r")
        self.csv_reader = csv.reader(self.openfile)

        header = next(self.csv_reader)

        self.logic_channels = header[1:]
        self.analog_channels = []
        self.samplecount = None
        if samplecount:
            self.samplecount = int(samplecount)
        self.samplerate = 500_000_000

        self.last_sample = 0
        self.start_samplenum = None
        self.next_samplenum = 0
        self.next_sample = 0
        self.samplenum = 0
        for row in self.csv_reader:
            self.next_samplenum = int(float(row[0]) * self.samplerate)
            self.last_sample = self.next_sample
            self.next_sample = 0
            for bit, value in enumerate(row[1:]):
                self.next_sample |= (1 if value == "1" else 0) << bit
            if self.next_samplenum >= 0:
                break

    def wait(self, conds=[]):
        if conds is None:
            conds = []
        self.matched = [False]
        while not any(self.matched):
            self.matched = [False] * (len(conds) if conds else 1)
            for i, cond in enumerate(conds):
                if "skip" in cond and cond["skip"] <= (self.next_samplenum - self.samplenum):
                    self.matched[i] = cond["skip"] == 0
                    self.samplenum += cond["skip"]
                    continue

            if any(self.matched):
                break

            self.samplenum = self.next_samplenum
            if self.start_samplenum is not None:
                self.put(self.start_samplenum, self.samplenum, OUTPUT_PYTHON, ["logic", self.last_sample])
                if self.samplecount is not None:
                    self.samplecount -= 1
                    if self.samplecount == 0:
                        raise EOFError()
            sample = self.next_sample

            try:
                row = next(self.csv_reader)
            except StopIteration:
                raise EOFError()

            self.next_samplenum = int(float(row[0]) * self.samplerate)
            self.next_sample = 0
            for bit, value in enumerate(row[1:]):
                self.next_sample |= (1 if value == "1" else 0) << bit

            # if self.analog_channels:
            #     self.put(self.samplenum, self.samplenum + 1, OUTPUT_PYTHON, ["analog"] + self.get_analog_values(self.samplenum))

            for i, cond in enumerate(conds):
                self.matched[i] = cond_matches(cond, self.last_sample, sample)
            self.last_sample = sample
            self.start_samplenum = self.samplenum

        bits = []
        for b in range(len(self.logic_channels)):
            bits.append((sample >> b) & 0x1)

        return tuple(bits)

    def get_analog_values(self, samplenum):
        if samplenum >= (self._analog_offset + self._analog_chunk_len):
            self._analog_offset += self._analog_chunk_len
            self._analog_file_index += 1
            self._analog_data = []
            total_logic = len(self.logic_channels)
            total_analog = len(self.analog_channels)
            for c in range(total_logic + 1, total_logic + 1 + total_analog):
                self._analog_data.append(self.zip.read(f"analog-1-{c}-{self._analog_file_index}"))
            self._analog_chunk_len = len(self._analog_data[0]) // 4

        values = []
        for data in self._analog_data:
            values.append(struct.unpack_from("f", data, (samplenum - self._analog_offset) * 4)[0])

        return values
