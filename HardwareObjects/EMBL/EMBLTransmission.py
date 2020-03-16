#
#  Project: MXCuBE
#  https://github.com/mxcube.
#
#  This file is part of MXCuBE software.
#
#  MXCuBE is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  MXCuBE is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with MXCuBE. If not, see <http://www.gnu.org/licenses/>.


import gevent
from HardwareRepository.HardwareObjects.abstract.AbstractTransmission import (
    AbstractTransmission,
)


class EMBLTransmission(AbstractTransmission):
    def __init__(self, name):
        AbstractTransmission.__init__(self, name)

        self.chan_att_value = None
        self.chan_att_state = None
        self.chan_att_limits = None

    def init(self):
        self.chan_att_value = self.get_channel_obect("chanValue")
        self.chan_att_value.connectSignal("update", self.value_changed)
        self.chan_att_state = self.get_channel_obect("chanState")
        self.chan_att_state.connectSignal("update", self.state_changed)
        self.chan_att_limits = self.get_channel_obect("chanLimits")
        self.chan_att_limits.connectSignal("update", self.limits_changed)

        self.update_values()

    def state_changed(self, state):
        self._state = state
        self.emit("stateChanged", self._state)

    def value_changed(self, value):
        self._value = value
        self.emit("valueChanged", self._value)

    def limits_changed(self, value):
        self._limits = value
        self.emit("limitsChanged", (self._limits,))

    def _set_value(self, value, timeout=None):
        self.chan_att_value.setValue(value)
