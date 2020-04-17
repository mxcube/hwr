#! /usr/bin/env python
# encoding: utf-8
#
# This file is part of MXCuBE.
#
# MXCuBE is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# MXCuBE is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with MXCuBE.  If not, see <https://www.gnu.org/licenses/>.
"""
"""

from __future__ import division, absolute_import
from __future__ import print_function, unicode_literals

__copyright__ = """ Copyright © 2016 - 2020 by MXCuBE Collaboration """
__license__ = "LGPLv3+"
__author__ = "rhfogh"
__date__ = "09/04/2020"

import abc
import pytest
from HardwareRepository.HardwareObjects.abstract.testing import TestAbstractActuatorBase

test_object = TestAbstractActuatorBase.test_object


class TestAbstractMotorBase(TestAbstractActuatorBase.TestAbstractActuatorBase):
    """Tests for AbstractMotor subclasses"""

    __metaclass__ = abc.ABCMeta

    def test_valocity(self, test_object):
        velocity = test_object.get_velocity()
        if velocity:
            vel2 = 0.9 * velocity
            test_object.set_velocity(vel2)
            assert (
                test_object.get_velocity() == vel2
            ), "Velocity set to %s ut remains as %s" % (vel2, velocity)

    def test_attribute_types(self, test_object):
        value = test_object.get_value()
        assert value is None or isinstance(value, (int, float)), (
            "AbstractMotor.value must be int, flost, or None, was %s" % value
        )

        limits = test_object.get_limits()
        assert isinstance(limits, tuple), "get_limits() must return a tuple"
        for lim in limits:
            assert lim is None or isinstance(lim, (int, float)), (
                "AbstractMotor.limits must be int, flost, or None, was %s" % lim
            )

    def test_validate_value(self, test_object):
        super(TestAbstractMotorBase, self).test_validate_value(test_object)

        if test_object.read_only:
            return

        limits = test_object.get_limits()
        if None in limits or limits[0] == limits[1]:
            limits = (0, 1)
        low, high = limits
        tol = test_object._tolerance
        mid = (low + high) / 2

        test_object.set_value(high, timeout=None)
        val = test_object.get_value()
        if tol:
            assert (
                abs(val - high) < tol
            ), "Error setting value to upper limit %s, result %s" % (high, val)

        test_object.update_value(mid)
        val = test_object.get_value()
        if tol:
            assert abs(val - mid) < tol, "Error updating value to %s, result %s" % (
                mid,
                val,
            )

        toobig = high + 0.1 * (high - low)
        assert not test_object.validate_value(toobig), (
            "Too-big value %s validates as OK" % toobig
        )
        with pytest.raises(ValueError):
            test_object.set_value(toobig, timeout=None)

        test_object._set_value(low)
        test_object.wait_ready()
        test_object.set_value_relative(0.5 * (high - low), timeout=None)
        val = test_object.get_value()
        if tol:
            assert abs(val - mid) < tol, (
                "set_value_relative result %s more than %s from target %s"
                % (val, tol, mid)
            )

        test_object.update_value(mid)
        assert test_object._nominal_value == mid, (
            "update_value result %s differs from target %s"
            % (test_object._nominal_value, mid)
        )

        if tol:
            test_object.update_value(low)
            test_object.update_value(low + 0.5 * tol)
            assert (
                test_object._nominal_value == low
            ), "update_value result does not respect tolerance cutoff"

    def test_setting_timeouts_1(self, test_object):
        # NB this test may need adjusting
        if test_object.read_only:
            return
        limits = test_object.get_limits()
        if None in limits or limits[0] == limits[1]:
            limits = (0, 1)
        low, high = limits

        test_object.set_value(low, timeout=90)
        with pytest.raises(BaseException):
            test_object.set_value(high, timeout=1.0e-6)

    def test_setting_timeouts_2(self, test_object):
        # NB this test may need adjusting
        if test_object.read_only:
            return
        limits = test_object.get_limits()
        if None in limits or limits[0] == limits[1]:
            limits = (0, 1)
        low, high = limits

        test_object.set_value(high, timeout=None)
        with pytest.raises(BaseException):
            test_object.set_value(low, timeout=0)
            test_object.wait_ready(timeout=1.0e-6)