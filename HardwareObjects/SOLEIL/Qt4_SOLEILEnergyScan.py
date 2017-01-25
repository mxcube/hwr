
from PyQt4 import QtGui
from PyQt4 import QtCore

from HardwareRepository.BaseHardwareObjects import Equipment
from HardwareRepository.TaskUtils import *

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

import logging
import PyChooch
import os
import time
import types
import math
import gevent
import Xanes

class Qt4_SOLEILEnergyScan(Equipment):
    def init(self):
        logging.getLogger("HWR").info('#############################    EnergyScan: INIT HWOBJ  ###################')
        self.ready_event = gevent.event.Event()
        self.scanning = None
        self.moving = None
        self.energyMotor = None
        self.energyScanArgs = None
        self.archive_prefix = None
        self.energy2WavelengthConstant=None
        self.defaultWavelength=None
        self._element = None
        self._edge = None
        self.doEnergyScan = None
        try:
            self.defaultWavelengthChannel=self.getChannelObject('default_wavelength')
        except KeyError:
            self.defaultWavelengthChannel=None
        else:
            if self.defaultWavelengthChannel is not None:
                self.defaultWavelengthChannel.connectSignal("connected", self.sConnected) 
                self.defaultWavelengthChannel.connectSignal("disconnected", self.sDisconnected)

        if self.defaultWavelengthChannel is None:
            #MAD beamline
            try:
                self.energyScanArgs=self.getChannelObject('escan_args')
            except KeyError:
                logging.getLogger("HWR").warning('EnergyScan: error initializing energy scan arguments (missing channel)')
                self.energyScanArgs=None

            try:
                self.scanStatusMessage=self.getChannelObject('scanStatusMsg')
            except KeyError:
                self.scanStatusMessage=None
                logging.getLogger("HWR").warning('EnergyScan: energy messages will not appear (missing channel)')
            else:
                self.connect(self.scanStatusMessage,'update',self.scanStatusChanged)

            try:
                self.doEnergyScan.connectSignal('commandReplyArrived', self.scanCommandFinished)
                self.doEnergyScan.connectSignal('commandBeginWaitReply', self.scanCommandStarted)
                self.doEnergyScan.connectSignal('commandFailed', self.scanCommandFailed)
                self.doEnergyScan.connectSignal('commandAborted', self.scanCommandAborted)
                self.doEnergyScan.connectSignal('commandReady', self.scanCommandReady)
                self.doEnergyScan.connectSignal('commandNotReady', self.scanCommandNotReady)
            except AttributeError,diag:
                logging.getLogger("HWR").warning('EnergyScan: error initializing energy scan (%s)' % str(diag))
                self.doEnergyScan = Xanes #.xanes(None, None) #None
            else:
                self.doEnergyScan.connectSignal("connected", self.sConnected)
                self.doEnergyScan.connectSignal("disconnected", self.sDisconnected)

            self.energyMotor=self.getObjectByRole("energy")
            self.resolutionMotor=self.getObjectByRole("resolution")
            self.previousResolution=None
            self.lastResolution=None

            self.dbConnection=self.getObjectByRole("dbserver")
            if self.dbConnection is None:
                logging.getLogger("HWR").warning('EnergyScan: you should specify the database hardware object')
            self.scanInfo=None

            self.transmissionHO=self.getObjectByRole("transmission")
            if self.transmissionHO is None:
                logging.getLogger("HWR").warning('EnergyScan: you should specify the transmission hardware object')

            self.cryostreamHO=self.getObjectByRole("cryostream")
            if self.cryostreamHO is None:
                logging.getLogger("HWR").warning('EnergyScan: you should specify the cryo stream hardware object')

            self.machcurrentHO=self.getObjectByRole("machcurrent")
            if self.machcurrentHO is None:
                logging.getLogger("HWR").warning('EnergyScan: you should specify the machine current hardware object')

            self.fluodetectorHO=self.getObjectByRole("fluodetector")
            if self.fluodetectorHO is None:
                logging.getLogger("HWR").warning('EnergyScan: you should specify the fluorescence detector hardware object')

            try:
                #self.moveEnergy.connectSignal('commandReplyArrived', self.moveEnergyCmdFinished)
                #self.moveEnergy.connectSignal('commandBeginWaitReply', self.moveEnergyCmdStarted)
                #self.moveEnergy.connectSignal('commandFailed', self.moveEnergyCmdFailed)
                #self.moveEnergy.connectSignal('commandAborted', self.moveEnergyCmdAborted)
                self.moveEnergy.connectSignal('commandReady', self.moveEnergyCmdReady)
                self.moveEnergy.connectSignal('commandNotReady', self.moveEnergyCmdNotReady)
            except AttributeError,diag:
                logging.getLogger("HWR").warning('EnergyScan: error initializing move energy (%s)' % str(diag))
                self.moveEnergy=None

            if self.energyMotor is not None:
                self.energyMotor.connect('positionChanged', self.energyPositionChanged)
                self.energyMotor.connect('stateChanged', self.energyStateChanged)
                self.energyMotor.connect('limitsChanged', self.energyLimitsChanged)
            if self.resolutionMotor is None:
                logging.getLogger("HWR").warning('EnergyScan: no resolution motor (unable to restore it after moving the energy)')
            else:
                self.resolutionMotor.connect('positionChanged', self.resolutionPositionChanged)

        self.thEdgeThreshold = self.getProperty("theoritical_edge_threshold")
        if self.thEdgeThreshold is None:
           self.thEdgeThreshold = 0.01
        
        if self.isConnected():
           self.sConnected()
        logging.getLogger("HWR").info('#############################    EnergyScan: INIT HWOBJ IS FINISHED ###################')

    def isConnected(self):
        if self.defaultWavelengthChannel is not None:
          # single wavelength beamline
          try:
            return self.defaultWavelengthChannel.isConnected()
          except:
            return False
        else:
          try:
            return self.doEnergyScan.isConnected()
          except:
            return False

    def resolutionPositionChanged(self,res):
        self.lastResolution=res

    def energyStateChanged(self, state):
        if state == self.energyMotor.READY:
          if self.resolutionMotor is not None:
            self.resolutionMotor.dist2res()
    
    # Handler for spec connection
    def sConnected(self):
        self.emit('connected', ())

    # Handler for spec disconnection
    def sDisconnected(self):
        self.emit('disconnected', ())

    def setElement(self):
        logging.getLogger("HWR").debug('EnergyScan: setElement')
        self.emit('setElement', (self._element, self._edge))
        
    def newPoint(self, x, y):
        logging.getLogger("HWR").debug('EnergyScan:newPoint')
        logging.info('EnergyScan newPoint %s, %s' % (x, y))
        self.emit('addNewPoint', (x, y))
        self.emit('newScanPoint', (x, y))

    def newScan(self,scanParameters):
        logging.getLogger("HWR").debug('EnergyScan:newScan')
        self.emit('newScan', (scanParameters,))

    # Energy scan commands
    def canScanEnergy(self):
        if not self.isConnected():
            return False
        if self.energy2WavelengthConstant is None or self.energyScanArgs is None:
            return False
        return self.doEnergyScan is not None
        
    def startEnergyScan(self,element,edge,directory,prefix,session_id=None,blsample_id=None):
        self._element = element
        self._edge = edge
        logging.getLogger("HWR").debug('EnergyScan: starting energy scan %s, %s' % (self._element, self._edge))
        self.setElement()
        self.xanes = Xanes.xanes(self, element, edge, directory, prefix, session_id, blsample_id, plot=False, test=False)
        self.scanInfo={"sessionId":session_id,"blSampleId":blsample_id,"element":element,"edgeEnergy":edge}
        if self.fluodetectorHO is not None:
            self.scanInfo['fluorescenceDetector']=self.fluodetectorHO.userName()
        if not os.path.isdir(directory):
            logging.getLogger("HWR").debug("EnergyScan: creating directory %s" % directory)
            try:
                os.makedirs(directory)
            except OSError,diag:
                logging.getLogger("HWR").error("EnergyScan: error creating directory %s (%s)" % (directory,str(diag)))
                self.emit('scanStatusChanged', ("Error creating directory",))
                return False

        scanParameter = {}
        scanParameter['title'] = "Energy Scan"
        scanParameter['xlabel'] = "Energy in keV"
        scanParameter['ylabel'] = "Normalized counts"
        self.newScan(scanParameter)

        #try:
            #curr=self.energyScanArgs.getValue()
        #except:
            #logging.getLogger("HWR").exception('EnergyScan: error getting energy scan parameters')
            #self.emit('scanStatusChanged', ("Error getting energy scan parameters",))
            #return False
        #try:
            #curr["escan_dir"]=directory
            #curr["escan_prefix"]=prefix
        #except TypeError:
        curr={}
        curr["escan_dir"]=directory
        curr["escan_prefix"]=prefix

        self.archive_prefix = prefix

        try:
            #self.energyScanArgs.setValue(curr)
            logging.getLogger("HWR").debug('EnergyScan: current energy scan parameters (%s, %s, %s, %s)' % (element, edge, directory, prefix))
        except:
            logging.getLogger("HWR").exception('EnergyScan: error setting energy scan parameters')
            self.emit('scanStatusChanged', ("Error setting energy scan parameters",))
            return False
        try:
            #self.doEnergyScan("%s %s" % (element,edge))
            self.scanCommandStarted()
            self.xanes.scan() #start() #scan()
            self.scanCommandFinished('success')
        except:
            import traceback
            logging.getLogger("HWR").error('EnergyScan: problem calling sequence %s' % traceback.format_exc())
            self.emit('scanStatusChanged', ("Error problem spec macro",))
            return False
        return True
    
    def cancelEnergyScan(self, *args):
        logging.info('SOLEILEnergyScan: canceling the scan')
        if self.scanning:
            #self.doEnergyScan.abort()
            self.xanes.abort()
            self.ready_event.set()
    
    def scanCommandReady(self):
        if not self.scanning:
            self.emit('energyScanReady', (True,))
    
    def scanCommandNotReady(self):
        if not self.scanning:
            self.emit('energyScanReady', (False,))
    
    def scanCommandStarted(self, *args):
        self.scanInfo['startTime']=time.strftime("%Y-%m-%d %H:%M:%S")
        self.scanning = True
        self.emit('energyScanStarted', ())
    
    def scanCommandFailed(self, *args):
        self.scanInfo['endTime']=time.strftime("%Y-%m-%d %H:%M:%S")
        self.scanning = False
        self.storeEnergyScan()
        self.emit('energyScanFailed', ())
        self.ready_event.set()
    
    def scanCommandAborted(self, *args):
        self.emit('energyScanFailed', ())
        self.ready_event.set()
    
    def scanCommandFinished(self, result, *args):
        logging.getLogger("HWR").debug("EnergyScan: energy scan result is %s" % result)
        with cleanup(self.ready_event.set):
            self.scanInfo['endTime']=time.strftime("%Y-%m-%d %H:%M:%S")
            logging.getLogger("HWR").debug("EnergyScan: energy scan result is %s" % result)
            self.scanning = False
            if result==-1:
                self.storeEnergyScan()
                self.emit('energyScanFailed', ())
                return

            try:
              t = float(result["transmissionFactor"])
            except:
              pass
            else:
              self.scanInfo["transmissionFactor"]=t
            try:
                et=float(result['exposureTime'])
            except:
                pass
            else:
                self.scanInfo["exposureTime"]=et
            try:
                se=float(result['startEnergy'])
            except:
                pass
            else:
                self.scanInfo["startEnergy"]=se
            try:
                ee=float(result['endEnergy'])
            except:
                pass
            else:
                self.scanInfo["endEnergy"]=ee

            try:
                bsX=float(result['beamSizeHorizontal'])
            except:
                pass
            else:
                self.scanInfo["beamSizeHorizontal"]=bsX

            try:
                bsY=float(result['beamSizeVertical'])
            except:
                pass
            else:
                self.scanInfo["beamSizeVertical"]=bsY

            try:
                self.thEdge=float(result['theoreticalEdge'])/1000.0
            except:
                pass

            self.emit('energyScanFinished', (self.scanInfo,))
            time.sleep(0.1)
            self.emit('energyScanFinished2', (self.scanInfo,))

    def doChooch(self, elt, edge, scanArchiveFilePrefix, scanFilePrefix):
        #symbol = "_".join((elt, edge))
        #scanArchiveFilePrefix = "_".join((scanArchiveFilePrefix, symbol))

        #i = 1
        #while os.path.isfile(os.path.extsep.join((scanArchiveFilePrefix + str(i), "raw"))):
            #i = i + 1

        #scanArchiveFilePrefix = scanArchiveFilePrefix + str(i) 
        #archiveRawScanFile=os.path.extsep.join((scanArchiveFilePrefix, "raw"))
        rawScanFile=os.path.extsep.join((scanFilePrefix, "raw"))
        scanFile=os.path.extsep.join((scanFilePrefix, "efs"))
        logging.info('SOLEILEnergyScan doChooch rawScanFile %s, scanFile %s' % (rawScanFile, scanFile))
        #if not os.path.exists(os.path.dirname(scanArchiveFilePrefix)):
            #os.makedirs(os.path.dirname(scanArchiveFilePrefix))
        
        #try:
            #f=open(rawScanFile, "w")
            #pyarch_f=open(archiveRawScanFile, "w")
        #except:
            #logging.getLogger("HWR").exception("could not create raw scan files")
            #self.storeEnergyScan()
            #self.emit("energyScanFailed", ())
            #return
        #else:
            #scanData = []
            
            #if scanObject is None:                
                #raw_data_file = os.path.join(os.path.dirname(scanFilePrefix), 'data.raw')
                #try:
                    #raw_file = open(raw_data_file, 'r')
                #except:
                    #self.storeEnergyScan()
                    #self.emit("energyScanFailed", ())
                    #return
                
                #for line in raw_file.readlines()[2:]:
                    #(x, y) = line.split('\t')
                    #x = float(x.strip())
                    #y = float(y.strip())
                    #x = x < 1000 and x*1000.0 or x
                    #scanData.append((x, y))
                    #f.write("%f,%f\r\n" % (x, y))
                    #pyarch_f.write("%f,%f\r\n"% (x, y))
            #else:
                #for i in range(len(scanObject.x)):
                    #x = float(scanObject.x[i])
                    #x = x < 1000 and x*1000.0 or x 
                    #y = float(scanObject.y[i])
                    #scanData.append((x, y))
                    #f.write("%f,%f\r\n" % (x, y))
                    #pyarch_f.write("%f,%f\r\n"% (x, y)) 

            #f.close()
            #pyarch_f.close()
            #self.scanInfo["scanFileFullPath"]=str(archiveRawScanFile)
        scanData = self.xanes.raw
        logging.info('scanData %s' % scanData)
        logging.info('PyChooch file %s' % PyChooch.__file__)
        pk, fppPeak, fpPeak, ip, fppInfl, fpInfl, chooch_graph_data = PyChooch.calc(scanData, elt, edge, scanFile)
        rm=(pk+30)/1000.0
        pk=pk/1000.0
        savpk = pk
        ip=ip/1000.0
        comm = ""

        self.thEdge = self.xanes.e_edge
        logging.getLogger("HWR").info("th. Edge %s ; chooch results are pk=%f, ip=%f, rm=%f" % (self.thEdge, pk,ip,rm))
        logging.info('math.fabs(self.thEdge - ip) %s' % math.fabs(self.thEdge - ip))
        logging.info('self.thEdgeThreshold %s' % self.thEdgeThreshold)
        
        logging.getLogger("HWR").warning('EnergyScan: calculated peak (%f) is more that 20eV %s the theoretical value (%f). Please check your scan and choose the energies manually' % (savpk, (self.thEdge - ip) < self.thEdgeThreshold and "below" or "above", self.thEdge))
        
        if math.fabs(self.thEdge - ip) > self.thEdgeThreshold:
          logging.info('Theoretical edge too different from the one just determined')
          pk = 0
          ip = 0
          rm = self.thEdge + 0.03
          comm = 'Calculated peak (%f) is more that 10eV away from the theoretical value (%f). Please check your scan' % (savpk, self.thEdge)
   
          logging.getLogger("HWR").warning('EnergyScan: calculated peak (%f) is more that 20eV %s the theoretical value (%f). Please check your scan and choose the energies manually' % (savpk, (self.thEdge - ip) < self.thEdgeThreshold and "below" or "above", self.thEdge))

        archiveEfsFile=os.path.extsep.join((scanArchiveFilePrefix, "efs"))

        logging.info('archiveEfsFile %s' % archiveEfsFile)

        # Check access to archive directory
        dirname = os.path.dirname(archiveEfsFile)
        if not os.path.exists(dirname): 
            try:
               os.makedirs( dirname )
               logging.getLogger("user_level_log").info( "Chooch. Archive path (%s) created"  % dirname)
            except OSError:
               logging.getLogger("user_level_log").error( "Chooch. Archive path is not accessible (%s)" % dirname)
               return None
            except:
               import traceback
               logging.getLogger("user_level_log").error( "Error creating archive path (%s) \n   %s" % (dirname, traceback.format_exc()))
               return None
        else:
            if not os.path.isdir(dirname):
               logging.getLogger("user_level_log").error( "Chooch. Archive path does not seem to be a valid directory (%s)" % dirname)
               return None

        try:
          fi=open(scanFile)
          fo=open(archiveEfsFile, "w")
        except:
          import traceback
          logging.getLogger("user_level_log").error( traceback.format_exc())
          self.storeEnergyScan()
          self.emit("energyScanFailed", ())
          return None
        else:
          fo.write(fi.read())
          fi.close()
          fo.close()

        logging.info('archive saved')
        self.scanInfo["peakEnergy"]=pk
        self.scanInfo["inflectionEnergy"]=ip
        self.scanInfo["remoteEnergy"]=rm
        self.scanInfo["peakFPrime"]=fpPeak
        self.scanInfo["peakFDoublePrime"]=fppPeak
        self.scanInfo["inflectionFPrime"]=fpInfl
        self.scanInfo["inflectionFDoublePrime"]=fppInfl
        self.scanInfo["comments"] = comm
        logging.info('self.scanInfo %s' % self.scanInfo)
        
        logging.info('chooch_graph_data %s' % str(chooch_graph_data))
        chooch_graph_x, chooch_graph_y1, chooch_graph_y2 = zip(*chooch_graph_data)
        chooch_graph_x = list(chooch_graph_x)
        logging.info('chooch_graph_x %s' %  str(chooch_graph_x))
        for i in range(len(chooch_graph_x)):
          chooch_graph_x[i]=chooch_graph_x[i]/1000.0

        logging.getLogger("HWR").info("<chooch> Saving png" )
        # prepare to save png files
        title="%10s  %6s  %6s\n%10s  %6.2f  %6.2f\n%10s  %6.2f  %6.2f" % ("energy", "f'", "f''", pk, fpPeak, fppPeak, ip, fpInfl, fppInfl) 
        fig=Figure(figsize=(15, 11))
        ax=fig.add_subplot(211)
        ax.set_title("%s\n%s" % (scanFile, title))
        ax.grid(True)
        ax.plot(*(zip(*scanData)), **{"color":'black'})
        ax.set_xlabel("Energy")
        ax.set_ylabel("MCA counts")
        ax2=fig.add_subplot(212)
        ax2.grid(True)
        ax2.set_xlabel("Energy")
        ax2.set_ylabel("")
        handles = []
        handles.append(ax2.plot(chooch_graph_x, chooch_graph_y1, color='blue'))
        handles.append(ax2.plot(chooch_graph_x, chooch_graph_y2, color='red'))
        canvas=FigureCanvasAgg(fig)

        escan_png = os.path.extsep.join((scanFilePrefix, "png"))
        escan_archivepng = os.path.extsep.join((scanArchiveFilePrefix, "png")) 
        self.scanInfo["jpegChoochFileFullPath"]=str(escan_archivepng)
        try:
          logging.getLogger("HWR").info("Rendering energy scan and Chooch graphs to PNG file : %s", escan_png)
          canvas.print_figure(escan_png, dpi=80)
        except:
          logging.getLogger("HWR").exception("could not print figure")
        try:
          logging.getLogger("HWR").info("Saving energy scan to archive directory for ISPyB : %s", escan_archivepng)
          canvas.print_figure(escan_archivepng, dpi=80)
        except:
          logging.getLogger("HWR").exception("could not save figure")

        self.storeEnergyScan()
        self.scanInfo=None

        logging.getLogger("HWR").info("<chooch> returning" )
        self.emit('chooch_finished', (pk, fppPeak, fpPeak, ip, fppInfl, fpInfl, rm, chooch_graph_x, chooch_graph_y1, chooch_graph_y2, title))
        self.choochResults = pk, fppPeak, fpPeak, ip, fppInfl, fpInfl, rm, chooch_graph_x, chooch_graph_y1, chooch_graph_y2, title
        return pk, fppPeak, fpPeak, ip, fppInfl, fpInfl, rm, chooch_graph_x, chooch_graph_y1, chooch_graph_y2, title

    def scanStatusChanged(self,status):
        self.emit('scanStatusChanged', (status,))
    
    def storeEnergyScan(self):
        #self.xanes.saveDat()
        self.xanes.saveRaw()
        self.xanes.saveResults()
        
        #if self.dbConnection is None:
            #return
        #try:
            #session_id=int(self.scanInfo['sessionId'])
        #except:
            #return
        #gevent.spawn(StoreEnergyScanThread, self.dbConnection,self.scanInfo)
        logging.info('SOLEILEnergyScan storeEnergyScan OK')
        #self.storeScanThread.start()

    def updateEnergyScan(self,scan_id,jpeg_scan_filename):
        pass

    # Move energy commands
    def canMoveEnergy(self):
        return self.canScanEnergy()
    
    def getCurrentEnergy(self):
        if self.energyMotor is not None:
            try:
                return self.energyMotor.getPosition()
            except: 
                logging.getLogger("HWR").exception("EnergyScan: couldn't read energy")
                return None
        elif self.energy2WavelengthConstant is not None and self.defaultWavelength is not None:
            return self.energy2wavelength(self.defaultWavelength)

        return None


    def get_value(self):
        return self.getCurrentEnergy()
    
    
    def getEnergyLimits(self):
        lims=None
        if self.energyMotor is not None:
            if self.energyMotor.isReady():
                lims=self.energyMotor.getLimits()
        return lims
    
    def getCurrentWavelength(self):
        if self.energyMotor is not None:
            try:
                return self.energy2wavelength(self.energyMotor.getPosition())
            except:
                logging.getLogger("HWR").exception("EnergyScan: couldn't read energy")
                return None
        else:
            return self.defaultWavelength
    
    def getWavelengthLimits(self):
        lims=None
        if self.energyMotor is not None:
            if self.energyMotor.isReady():
                energy_lims=self.energyMotor.getLimits()
                lims=(self.energy2wavelength(energy_lims[1]),self.energy2wavelength(energy_lims[0]))
                if lims[0] is None or lims[1] is None:
                    lims=None
        return lims
    
    def startMoveEnergy(self,value,wait=True):
        logging.getLogger("HWR").info("Moving energy to (%s)" % value)
        try:
            value=float(value)
        except (TypeError,ValueError),diag:
            logging.getLogger("HWR").error("EnergyScan: invalid energy (%s)" % value)
            return False

        try:
            curr_energy=self.energyMotor.getPosition()
        except:
            logging.getLogger("HWR").exception("EnergyScan: couldn't get current energy")
            curr_energy=None

        if value!=curr_energy:
            logging.getLogger("HWR").info("Moving energy: checking limits")
            try:
                lims=self.energyMotor.getLimits()
            except:
                logging.getLogger("HWR").exception("EnergyScan: couldn't get energy limits")
                in_limits=False
            else:
                in_limits=value>=lims[0] and value<=lims[1]
                
            if in_limits:
                logging.getLogger("HWR").info("Moving energy: limits ok")
                self.previousResolution=None
                if self.resolutionMotor is not None:
                    try:
                        self.previousResolution=self.resolutionMotor.getPosition()
                    except:
                        logging.getLogger("HWR").exception("EnergyScan: couldn't get current resolution")
                self.moveEnergyCmdStarted()
                def change_egy():
                    try:
                        self.moveEnergy(value, wait=True)
                    except:
                        self.moveEnergyCmdFailed()
                    else:
                        self.moveEnergyCmdFinished(True)
                if wait:
                    change_egy()
                else:
                    gevent.spawn(change_egy)
            else:
                logging.getLogger("HWR").error("EnergyScan: energy (%f) out of limits (%s)" % (value,lims))
                return False          
        else:
            return None

        return True
    
    def startMoveWavelength(self,value, wait=True):
        energy_val=self.energy2wavelength(value)
        if energy_val is None:
            logging.getLogger("HWR").error("EnergyScan: unable to convert wavelength to energy")
            return False
        return self.startMoveEnergy(energy_val, wait)
    
    def cancelMoveEnergy(self):
        self.moveEnergy.abort()
    
    def energy2wavelength(self,val):
        if self.energy2WavelengthConstant is None:
            return None
        try:
            other_val=self.energy2WavelengthConstant/val
        except ZeroDivisionError:
            other_val=None
        return other_val
   
    def energyPositionChanged(self,pos):
        wav=self.energy2wavelength(pos)
        if wav is not None:
            self.emit('energyChanged', (pos,wav))
            self.emit('valueChanged', (pos, ))
    
    def energyLimitsChanged(self,limits):
        self.emit('energyLimitsChanged', (limits,))
        wav_limits=(self.energy2wavelength(limits[1]),self.energy2wavelength(limits[0]))
        if wav_limits[0]!=None and wav_limits[1]!=None:
            self.emit('wavelengthLimitsChanged', (wav_limits,))
        else:
            self.emit('wavelengthLimitsChanged', (None,))
    
    def moveEnergyCmdReady(self):
        if not self.moving:
            self.emit('moveEnergyReady', (True,))
    
    def moveEnergyCmdNotReady(self):
        if not self.moving:
            self.emit('moveEnergyReady', (False,))
    
    def moveEnergyCmdStarted(self):
        self.moving = True
        self.emit('moveEnergyStarted', ())
    
    def moveEnergyCmdFailed(self):
        self.moving = False
        self.emit('moveEnergyFailed', ())
    
    def moveEnergyCmdAborted(self):
        pass
        #self.moving = False
        #self.emit('moveEnergyFailed', ())
    
    def moveEnergyCmdFinished(self,result):
        self.moving = False
        self.emit('moveEnergyFinished', ())

    def getPreviousResolution(self):
        return (self.previousResolution,self.lastResolution)

    def restoreResolution(self):
        if self.resolutionMotor is not None:
            if self.previousResolution is not None:
                try:
                    self.resolutionMotor.move(self.previousResolution)
                except:
                    return (False,"Error trying to move the detector")
                else:
                    return (True,None)
            else:
                return (False,"Unknown previous resolution")
        else:
            return (False,"Resolution motor not defined")

    # Elements commands
    def getElements(self):
        elements=[]
        try:
            for el in self["elements"]:
                elements.append({"symbol":el.symbol, "energy":el.energy})
        except IndexError:
            pass
        return elements

    # Mad energies commands
    def getDefaultMadEnergies(self):
        energies=[]
        try:
            for el in self["mad"]:
                energies.append([float(el.energy), el.directory])
        except IndexError:
            pass
        return energies

def StoreEnergyScanThread(db_conn, scan_info):
    return
    scanInfo = dict(scan_info)
    dbConnection = db_conn
    
    blsampleid = scanInfo['blSampleId']
    scanInfo.pop('blSampleId')
    db_status=dbConnection.storeEnergyScan(scanInfo)
    if blsampleid is not None:
        try:
            energyscanid=int(db_status['energyScanId'])
        except:
            pass
        else:
            asoc={'blSampleId':blsampleid, 'energyScanId':energyscanid}
            dbConnection.associateBLSampleAndEnergyScan(asoc)
