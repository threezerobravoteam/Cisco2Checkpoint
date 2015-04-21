from ciscoconfparse import CiscoConfParse
from singleton import Singleton
from config import *
import xml.etree.ElementTree as et
import copy
import socket

def isarray(var):
	return isinstance(var, (list, tuple))
	
def isipaddress(var):
	try:
		socket.inet_aton(var)
		return True
	except socket.error:
		return False
		
class C2CException(Exception):
	pass
	
class CiscoObject():
	"""A name command"""
	name = None
	desc = None
	alias = []			# Alias name used to keep associations when objects
						# are merged from IP addresses.
	dbClass = None		# Used to determine checkpoint class	
						# Ex: 
	alreadyExist = False		# Flag to determine if it already exist in checkpoint database
			
	def __init__(self, name, desc=''):
		n = copy.deepcopy(name)
		self.name = self._sanitizeIllegalWords(self._sanitizeName(name))
		self.desc = desc
		self.alias = []
		self.addAlias(n)
		
	def __str__(self):
		return str(self.toString())
		
	def _parseChildren(self,parent):
		ret = {}
		for child in parent.children:
			a = child.text.split(' ', 2)
			if ret.has_key(a[1]):
				ret[a[1]].append(a[2])
			else:
				ret[a[1]] = []
				ret[a[1]].append(a[2])
		return ret
		
	def _sanitizeIllegalWords(self, text):
		for i, j in ILLEGAL_DIC.iteritems():
			text = text.replace(i, j)
		return text.rstrip()
		
	def _sanitizeName(self, name):
		if name != '' and name[0].isdigit():
			if self.getClass() == 'CiscoNet':
				return NEW_NET_PREFIX+name
			elif self.getClass() == 'CiscoName' or self.getClass() == 'CiscoHost':
				return NEW_HOST_PREFIX+name
			else:
				return name
		else:
			return name
			
	def getClass(self):
		return self.__class__.__name__
		
	def getDesc(self):
		if self.desc == None:
			return ''
		else:
			return str(self.desc.replace('"\/ ', '').replace(' \/"', ''))
		
	def addAlias(self,text):
		if text != None and text != self.name and not text in self.alias:
			#print('Add Alias: '+str(self.name)+' vs '+ text)
			self.alias.append(text)
		
	def toString(self, indent=''):
		return indent+self.getClass()+'(name=%s,desc=%s)' % (self.name,self.getDesc())
		
	def toDBEdit(self):
		return ''	
		
	def toDBEditElement(self, groupName):
		return ''
		
class CiscoPort(CiscoObject):
	"""A cisco port"""
	proto = None
	
	def __init__(self, name, alreadyExist=False):
		CiscoObject.__init__(self,name)
		self.alreadyExist = alreadyExist
		
	def _toDBEditType(self):
		if self.proto == 'tcp':
			return 'tcp_service'
		elif self.proto == 'udp':
			return 'udp_service'
		elif self.proto == 'any':
			return ''
		else:
			raise C2CException('Protocol not supported')
			
	def toDBEditElement(self, groupName):
		return "addelement services {0} '' services:{1}\n".format(groupName, self.name)

class CiscoGroup(CiscoObject):				
	members = []
	
	def __init__(self,name):
		self.members = []
		CiscoObject.__init__(self,name)
		
	def _convertPort(self, text):
		for i, j in PORT_DIC.iteritems():
			text = text.replace(i, j)
		return text.rstrip()
		
	def _getMemberObj(self, type, v1, v2=None, v3=None):
		c2c = Cisco2Checkpoint.getInstance()
		if type == 'host' and v1 == 'any':
			name = v1
			obj_list = c2c.findObjByName(name)
		elif type in ['port','tcp','udp'] and v1 == 'any':
			name = v1
			#obj_list = c2c.findIPServiceByName(name)
			obj_list = c2c.findObjByNameType(name,'CiscoAnyPort')
		#elif type == 'object-group':
		#	name = v1
		#	obj_list = c2c.findServiceByName(name)
		elif type == 'icmp':
			name = v1
			obj_list = c2c.findIcmpByName(name)
		elif type == 'icmp-object':
			name = v1
			obj_list = c2c.findIcmpByName(name)
		elif type == 'esp':
			name = v1
			obj_list = c2c.findObjByNameType(name,'CiscoEspProto')
		elif type == 'ah':
			name = v1
			obj_list = c2c.findObjByNameType(name,'CiscoAHProto')
		elif type == 'host':
			name = v1
			obj_list = c2c.findHostByAddr(name)
		elif type == 'protocol':
			name = v1
			obj_list = c2c.findIcmpByName(name)
		elif type == 'subnet':
			name,subnet,mask = v1,v1,v2
			obj_list = c2c.findNetByAddr(subnet,mask)
		elif type == 'object':
			name = v1
			obj_list = c2c.findObjByName(name)
		elif type == 'group':
			name = v1
			obj_list = c2c.findObjByName(name)
		elif type == 'eq':		# port-object eq X
			name,proto,port = v1+'/'+v2,v1,v2
			port = self._convertPort(port)
			if proto in ['tcp','udp']:
				obj_list = c2c.findServiceByNum(proto,port)
			elif proto == 'tcp-udp':
				obj_list1 = c2c.findServiceByNum('tcp',port)
				obj_list2 = c2c.findServiceByNum('udp',port)
				ret1 = self._parseResult(obj_list1, name, type)
				ret2 = self._parseResult(obj_list2, name, type)
				if ret1 and ret2:
					return obj_list1 + obj_list2
				else:
					return None					
		elif type == 'range':		# port-object range X Y
			name,proto,first,last = v1+'/'+v2+'-'+v3,v1,v2,v3
			if proto in ['tcp','udp']:
				obj_list = c2c.findServiceByRange(proto,first,last)
			elif proto == 'tcp-udp':
				obj_list1 = c2c.findServiceByRange('tcp',first,last)
				obj_list2 = c2c.findServiceByRange('udp',first,last)
				ret1 = self._parseResult(obj_list1, name, type)
				ret2 = self._parseResult(obj_list2, name, type)
				if ret1 and ret2:
					return obj_list1 + obj_list2
				else:
					return None
		elif type in ['static', 'dynamic']:				# Nat rules
			name = v1
			obj_list = c2c.findObjByName(name)
		else:
			name,subnet,mask = type+'/'+v1,type,v1		# Yes this is ugly. Thx cisco.
			type = 'subnet-mask'
			obj_list = c2c.findNetByAddr(subnet,mask)
						
		return self._parseResult(obj_list, name, type)

	def _parseResult(self,obj_list, name, type):
		if len(obj_list) == 1: 
			return obj_list[0]
		elif len(obj_list) > 1:
			if C2C_DEBUG: print(WARN_PREFIX+'Warning: Found %i instances of "%s" (%s)' % (len(obj_list),name,type))
			return obj_list[0]
		else:
			if C2C_DEBUG: print(WARN_PREFIX+'Warning: Could not find object "%s" (%s). The script will create it.' % (name,type))
			return None
			
	def _createMemberObj(self, type, v1, v2=None, v3=None):
		c2c = Cisco2Checkpoint.getInstance()
		if type == 'host' and v1 == 'any':
			newObj = CiscoAnyHost()
			c2c.addObj(newObj)
		elif type == 'port' and v1 == 'any':
			newObj = CiscoAnyPort()
			c2c.addObj(newObj)
		elif type == 'esp' and v1 == 'any':
			newObj = CiscoEspProto()
			c2c.addObj(newObj)
		elif type == 'ah' and v1 == 'any':
			newObj = CiscoAHProto()
			c2c.addObj(newObj)
		elif type == 'icmp':
			name = v1
			newObj = CiscoIcmp(name)
			c2c.addObj(newObj)
			self.members.append(newObj)
		elif type == 'icmp-object':
			name = v1
			newObj = CiscoIcmp(name)
			c2c.addObj(newObj)
			self.members.append(newObj)
		elif type == 'host':
			newObj = CiscoHost(None, NEW_HOST_PREFIX+v1, v1)
			c2c.addObj(newObj)
			self.members.append(newObj)
		elif type == 'subnet':
			subnet,mask = v1,v2
			newObj = CiscoNet(None, NEW_NET_PREFIX+subnet, subnet, mask)
			c2c.addObj(newObj)
			self.members.append(newObj)
		elif type == 'object':
			raise C2CException('Cannot create an object member "%s" on the fly.' % v1)
		elif type == 'group':
			raise C2CException('Cannot create an group member "%s" on the fly.' % v1)
		elif type == 'eq':		# port-object eq X
			proto,port = v1,v2
			port = self._convertPort(port)
			if proto in ['tcp','udp']:
				newObj = CiscoSinglePort(None, None, proto, port)
				c2c.addObj(newObj)
				self.members.append(newObj)
			elif proto == 'tcp-udp':
				name,proto,port = v1+'/'+v2,v1,v2
				obj_list1 = c2c.findServiceByNum('tcp',port)		# Redo the parsing because
				obj_list2 = c2c.findServiceByNum('udp',port)		# one of these could exist.
				ret1 = self._parseResult(obj_list1, name, 'tcp')
				ret2 = self._parseResult(obj_list2, name, 'udp')
				
				if ret1 == None:
					newObj1 = CiscoSinglePort(None, None, 'tcp', port)
					c2c.addObj(newObj1)
					self.members.append(newObj1)
				if ret2 == None:
					newObj2 = CiscoSinglePort(None, None, 'udp', port)
					c2c.addObj(newObj2)
					self.members.append(newObj2)

		elif type == 'range':		# port-object range X Y
			proto,first,last = v1,v2,v3
			if proto in ['tcp','udp']:			
				newObj = CiscoPortRange(None, None, proto, first, last)
				c2c.addObj(newObj)
				self.members.append(newObj)
			elif proto == 'tcp-udp':
				newObj1 = CiscoPortRange(None, None, 'tcp', first, last)
				newObj2 = CiscoPortRange(None, None, 'udp', first, last)
				c2c.addObj(newObj1)
				c2c.addObj(newObj2)
				self.members.append(newObj1)
				self.members.append(newObj2)
		elif type in ['static', 'dynamic']:				# Nat rules
			name = v1
			newObj = CiscoHost(None, name, name, None, True)
			c2c.addObj(newObj)
			#raise C2CException('Cannot create a nat external IP "%s" on the fly.' % name)
		else:
			subnet,mask = type,v1		# Yes this is ugly.
			newObj = CiscoNet(None, NEW_NET_PREFIX+subnet, subnet, mask)
			c2c.addObj(newObj)
			self.members.append(newObj)
		
	def isEqual(self, other):
		return self.__dict__ == other.__dict__
		
class CiscoName(CiscoObject):
	"""A cisco name"""
	ipAddr = None
	
	def __init__(self, parsedObj, name=None, ipAddr=None, desc=None, alreadyExist=False):
		if name != None:
			CiscoObject.__init__(self,name,desc)
			self.ipAddr = ipAddr
			self.alreadyExist = alreadyExist
		else:
			a = parsedObj.text.split(' ', 4)
			CiscoObject.__init__(self,a[2])
			self.ipAddr = a[1]
			if len(a) > 4:
				self.desc = a[4]
		self.dbClass = 'host_plain'
		#self.addAlias(self.ipAddr)
			
	def toString(self, indent=''):
		return indent+self.getClass()+"(name=%s,ipAddr=%s,desc=%s,alias=%s)\n" % (self.name,self.ipAddr,self.getDesc(),','.join(self.alias))

	def toDBEdit(self):
		return '''# Creating new host: {0}
 create host_plain {0}
 modify network_objects {0} ipaddr {1}
 modify network_objects {0} comments "{2}"
 update network_objects {0}
 '''.format(self.name, self.ipAddr, self.getDesc())
 
	def toDBEditElement(self, groupName):
		return "addelement network_objects {0} '' network_objects:{1}\n".format(groupName, self.name)

class CiscoHost(CiscoName):
	"""A cisco host"""
	
	def __init__(self, parsedObj, name=None, ipAddr=None, desc=None, alreadyExist=False):
		if name != None:
			CiscoName.__init__(self,None,name,ipAddr,desc,alreadyExist)
		else:
			a = parsedObj.text.split(' ', 2)
			CiscoName.__init__(self,parsedObj)
			child = self._parseChildren(parsedObj)
			self.ipAddr = child['host'][0]
			if child.has_key('description'):
				self.desc = child['description'][0]
			self.alreadyExist = alreadyExist
					
	def toString(self,indent=''):
		return indent+self.getClass()+"(name=%s,ipAddr=%s,desc=%s,alias=%s)\n" % (self.name,self.ipAddr,self.getDesc(),','.join(self.alias))
		
	def toDBEditElement(self, groupName):
		return "addelement network_objects {0} '' network_objects:{1}\n".format(groupName, self.name)

class CiscoAnyHost(CiscoHost):
	"""A cisco host"""
	
	def __init__(self):
		CiscoHost.__init__(self,None,'any',None,None,True)
		
class CiscoNet(CiscoObject):
	"""A cisco subnet"""
	ipAddr = None
	mask = None
	
	def __init__(self, parsedObj, name=None, ipAddr=None, mask=None, desc=None):
		if name != None:
			CiscoObject.__init__(self,name,desc)
			self.ipAddr = ipAddr
			self.mask = mask
		else:
			a = parsedObj.text.split(' ', 2)
			CiscoObject.__init__(self,a[2])
			child = self._parseChildren(parsedObj)
			self.ipAddr,self.mask = child['subnet'][0].split(' ',1)
			if child.has_key('description'):
				self.desc = child['description'][0]

		self.dbClass = 'network'
			
	def toString(self, indent=''):
		return indent+self.getClass()+"(name=%s,ipAddr=%s/%s,desc=%s,alias=%s)\n" % (self.name,self.ipAddr,self.mask,self.getDesc(),', '.join(self.alias))

	def toDBEdit(self):
		return '''# Creating new subnet: {0}
 create network {0}
 modify network_objects {0} ipaddr {1}
 modify network_objects {0} netmask {2}
 modify network_objects {0} comments "{3}"
 update network_objects {0}
 '''.format(self.name, self.ipAddr, self.mask, self.getDesc())
		
	def toDBEditElement(self, groupName):
		return "addelement network_objects {0} '' network_objects:{1}\n".format(groupName, self.name)

class CiscoRange(CiscoObject):
	"""A cisco range"""
	first = None
	last = None
	
	def __init__(self, parsedObj):
		a = parsedObj.text.split(' ', 2)
		CiscoObject.__init__(self,a[2])
		
		child = self._parseChildren(parsedObj)
		self.first,self.last = child['range'][0].split(' ',1)
		if child.has_key('description'):
			self.desc = child['description'][0]
				
		self.dbClass = 'address_range'
			
	def toString(self, indent=''):
		return indent+self.getClass()+"(name=%s,ipRange=%s/%s,desc=%s)\n" % (self.name,self.first,self.last,self.getDesc())

	def toDBEdit(self):
		return '''# Creating new range: {0}
 create address_range {0}
 modify network_objects {0} ipaddr_first {1}
 modify network_objects {0} ipaddr_last {2}
 modify network_objects {0} comments "{3}"
 update network_objects {0}
 '''.format(self.name, self.first, self.last, self.getDesc())		
		
	def toDBEditElement(self, groupName):
		return "addelement network_objects {0} '' network_objects:{1}\n".format(groupName, self.name)

class CiscoSinglePort(CiscoPort):
	"""A cisco name"""
	port = None
	
	def __init__(self, parsedObj, name=None, proto=None, port=None, desc=None, alreadyExist=False):
		if name != None:
			CiscoPort.__init__(self, name, alreadyExist)	
		else:
			if proto == 'tcp':
				CiscoPort.__init__(self, TCP_PREFIX+port, alreadyExist)
				self.dbClass = 'tcp_service'
			elif proto == 'udp':
				CiscoPort.__init__(self, UDP_PREFIX+port, alreadyExist)
				self.dbClass = 'udp_service'
			else:
				raise C2CException('Invalid Protocol: %s' % proto)
				
		if proto != None:
			self.proto = proto
			self.port = port
			self.desc = desc
		elif parsedObj != None:
			a = parsedObj.text.split(' ', 2)
			self.port = a[2]

	def toString(self, indent=''):
		return indent+self.getClass()+"(name=%s,port=%s,desc=%s,alias=%s)\n" % (self.name,self.port,self.getDesc(),', '.join(self.alias))

	def toDBEdit(self):
		return '''# Creating new port: {1}
 create {0} {1}
 modify services {1} port {2}
 modify services {1} comments "{3}"
 update services {1}
 '''.format(self._toDBEditType(), self.name, self.port, self.getDesc())
	
	def toDBEditElement(self, groupName):
		return "addelement services {0} '' services:{1}\n".format(groupName, self.name)

class CiscoAnyPort(CiscoSinglePort):
	"""A cisco port"""
	
	def __init__(self):
		CiscoSinglePort.__init__(self, None, 'any', None, 0, None, True)
		
class CiscoPortRange(CiscoPort):
	"""A cisco name"""
	first = None
	last = None
	
	def __init__(self, parsedObj, name=None, proto=None, first=None, last=None, desc=None, alreadyExist=False):
		if name == None:
			if proto == 'tcp':
				CiscoPort.__init__(self, TCP_PREFIX+first+'-'+last, alreadyExist)
			elif proto == 'udp':
				CiscoPort.__init__(self, UDP_PREFIX+first+'-'+last, alreadyExist)		
			else:
				raise C2CException('Invalid Protocol')
		else:
			CiscoPort.__init__(self, name)
			
		if proto != None:
			self.proto = proto
			self.first = first
			self.last = last
			self.desc = desc
		else:
			a = parsedObj.text.split(' ', 3)
			self.first = a[2]
			self.last = a[3]
		
	def toString(self, indent=''):
		return indent+self.getClass()+"(name=%s,port=%s-%s,desc=%s)\n" % (self.name,self.first,self.last,self.getDesc())
		
	def toDBEdit(self):
		return '''# Creating new port range: {1}
 create {0} {1}
 modify services {1} port {2}-{3}
 modify services {1} comments "{4}"
 update services {1}
 '''.format(self._toDBEditType(), self.name, self.first, self.last, self.getDesc())
	
	def toDBEditElement(self, groupName):
		return "addelement services {0} '' services:{1}\n".format(groupName, self.name)

class CiscoProto(CiscoPort):
	"""A cisco icmp packet"""
	
	def __init__(self, name=None, desc=None, alreadyExist=False):
		CiscoPort.__init__(self, name, alreadyExist)
		self.desc = desc

	def toString(self, indent=''):
		return indent+self.getClass()+"(name=%s,desc=%s,alias=%s)\n" % (self.name,self.getDesc(),', '.join(self.alias))

	def toDBEdit(self):
		return ''
	
	def toDBEditElement(self, groupName):
		return "addelement services {0} '' services:{1}\n".format(groupName, self.name)
		
class CiscoIcmp(CiscoProto):
	"""A cisco icmp packet"""
	
	def __init__(self, name=None, desc=None, alreadyExist=False):
		CiscoProto.__init__(self, name, desc, alreadyExist)
		self.dbClass = 'icmp_service'
		
class CiscoAnyIcmp(CiscoProto):
	"""A cisco icmp packet"""
	
	def __init__(self):
		CiscoProto.__init__(self, ANY_ICMP, None, True)
		self.addAlias('any')
	
class CiscoEspProto(CiscoProto):
	"""A cisco ESP protocol"""
	
	def __init__(self):
		CiscoProto.__init__(self, ANY_ESP, None, True)
		self.addAlias('any')
		
class CiscoAHProto(CiscoProto):
	"""A cisco AH protocol"""
	
	def __init__(self):
		CiscoProto.__init__(self, ANY_AH, None, True)
		self.addAlias('any')
		
class CiscoNetGroup(CiscoGroup):
	"""A cisco subnet"""
	
	def __init__(self, parsedObj):
		a = parsedObj.text.split(' ', 2)
		CiscoGroup.__init__(self,a[2])
		self.dbClass = 'network_object_group'
		
		child = self._parseChildren(parsedObj)
		# For all network objects
		if child.has_key('network-object'):
			for network in child['network-object']:
				# Possible values of network-object:
				# network-object 206.156.53.0 255.255.255.0
				# network-object object nG_IM2-NFA_10.253.252.145
				# network-object host 10.253.216.74
				v1,v2 = network.split(' ',1)
				obj = self._getMemberObj(v1,v2)
				if obj:
					self.members.append(obj)
				else:
					self._createMemberObj(v1,v2)
					
		# For all group objects
		if child.has_key('group-object'):
			for groupName in child['group-object']:
				obj = self._getMemberObj('group',groupName)
				if obj:
					self.members.append(obj)
				else:
					self._createMemberObj('group',groupName)
					
		if child.has_key('description'):
			self.desc = child['description'][0]
		
	def toString(self, indent=''):
		ret = indent+self.getClass()+"(name=%s,desc=%s,nbMembers=%i)\n" % (self.name,self.getDesc(),len(self.members))
		for member in self.members:
			ret += indent+' '+member.toString(indent)
		return ret

	def toDBEdit(self):
		ret = ''
		# Write header
		ret += '''# Creating new network group: {0}
 create network_object_group {0}
 modify network_objects {0} comments "{1}"
 '''.format(self.name, self.getDesc())
		# Write all members
		for mem in self.members:
			ret += mem.toDBEditElement(self.name)
		# Write footer
		ret += '''update network_objects {0}
 '''.format(self.name)
		return ret

	def toDBEditElement(self, groupName):
		return "addelement network_objects {0} '' network_objects:{1}\n".format(groupName, self.name)

class CiscoPortGroup(CiscoGroup):
	"""A cisco service"""
	
	def __init__(self, parsedObj):
		a = parsedObj.text.split(' ', 3)
		grpType = a[1]
		name = a[2]
		CiscoGroup.__init__(self,name)
		self.dbClass = 'service_group'
		
		if grpType == 'protocol':
			child = self._parseChildren(parsedObj)
			if child.has_key('protocol-object'):
				if ('tcp' in child['protocol-object'] and 'udp' in child['protocol-object']) \
				  or 'ip' in child['protocol-object']:
					obj = self._getMemberObj('port','any')
					if obj:
						if isarray(obj):
							for o in obj:
								self.members.append(o)
						else:
							self.members.append(obj)
					else:
						self._createMemberObj('port','any')

		else:
			child = self._parseChildren(parsedObj)
			# For all portObj objects
			if child.has_key('port-object'):
				# if port-object, group object-group should contain a protocol
				proto = a[3]
				for portObj in child['port-object']:
					# Possible values of port-object:
					# port-object range 8194 8198
					# port-object eq 4321
					# port-object eq whois
					portCmp,port = portObj.split(' ',1)
					port = self._convertPort(port)
					if ' ' in port:		# After conversion, the port could be a range (ex: sip)
						portCmp = 'range'
						
					if portCmp == 'eq':
						obj = self._getMemberObj(portCmp,proto,port)
					elif portCmp == 'range':
						first,last = port.split(' ',1)
						obj = self._getMemberObj(portCmp,proto,first,last)
					else:
						raise C2CException('This identifier is not supported: %s' % portCmp)
						
					if obj:
						if isarray(obj):
							for o in obj:
								self.members.append(o)
						else:
							self.members.append(obj)
					else:
						if portCmp == 'eq':
							self._createMemberObj(portCmp,proto,port)
						elif portCmp == 'range':
							self._createMemberObj(portCmp,proto,first,last)
						else:
							raise C2CException('This identifier is not supported: %s' % portCmp)

			if child.has_key('service-object'):
				for portObj in child['service-object']:
					# Possible values of service-object:
					# service-object tcp destination range 19305 19309 
					# service-object udp destination eq 123
					# service-object udp destination eq whois
					# service-object icmp 
					portObj = portObj.rstrip()
					if portObj == 'icmp': 		# This means all icmp. 
						portCmp = 'icmp'
						obj = self._getMemberObj(portCmp,'any')
					elif portObj == 'esp': 		# This means all icmp. 
						portCmp = 'esp'
						obj = self._getMemberObj(portCmp,'any')
					elif portObj == 'ah': 		# This means all icmp. 
						portCmp = 'ah'
						obj = self._getMemberObj(portCmp,'any')
					else:
						proto,direction,portCmp,port = portObj.split(' ',3)
						port = self._convertPort(port)
						if ' ' in port and port[-1:] != ' ':		# After conversion, the port could be a range (ex: sip)
							portCmp = 'range'
							
						if portCmp == 'eq':
							obj = self._getMemberObj(portCmp,proto,port)
						elif portCmp == 'range':
							first,last = port.split(' ',1)
							obj = self._getMemberObj(portCmp,proto,first,last)
						else:
							raise C2CException('This identifier is not supported: %s' % portCmp)
							
					if obj:
						if isarray(obj):
							for o in obj:
								self.members.append(o)
						else:
							self.members.append(obj)
					else:
						if portCmp == 'eq':
							self._createMemberObj(portCmp,proto,port)
						elif portCmp == 'range':
							self._createMemberObj(portCmp,proto,first,last)
						elif portCmp == 'icmp':
							self._createMemberObj(portCmp,'any')
						elif portCmp == 'esp':
							self._createMemberObj(portCmp,'any')
						elif portCmp == 'ah':
							self._createMemberObj(portCmp,'any')
						else:
							raise C2CException('This identifier is not supported: %s' % portCmp)
							
			if child.has_key('group-object'):
				for portObj in child['group-object']:
					# Possible values of group-object:
					# group-object RPC_High_ports_TCP
					obj = self._getMemberObj('group',portObj)
					if obj:
						if isarray(obj):
							for o in obj:
								self.members.append(o)
						else:
							self.members.append(obj)
					else:
						self._createMemberObj('group',portObj)
			
			if child.has_key('icmp-object'):
				proto = 'icmp'
				for icmpObj in child['icmp-object']:
					# icmp-object echo-reply
					# icmp-object time-exceeded
					# icmp-object unreachable
					# icmp-object echo
					obj = self._getMemberObj(proto,icmpObj)
					if obj:
						if isarray(obj):
							for o in obj:
								self.members.append(o)
						else:
							self.members.append(obj)
					else:
						self._createMemberObj(proto,icmpObj)
						
		if child.has_key('description'):
			self.desc = child['description'][0]
		
	def toString(self, indent=''):
		ret = indent+self.getClass()+"(name=%s,desc=%s,nbMembers=%i)\n" % (self.name,self.getDesc(),len(self.members))
		for member in self.members:
			ret += indent+' '+member.toString(indent)
		return ret

	def toDBEdit(self):
		ret = ''
		# Write header
		ret += '''# Creating new port group: {0}
 create service_group {0}
 modify services {0} comments "{1}"
 '''.format(self.name, self.getDesc())
		# Write all members
		for mem in self.members:
			ret += mem.toDBEditElement(self.name)
		# Write footer
		ret += '''update services {0}
 '''.format(self.name)
		return ret
	
	def toDBEditElement(self, groupName):
		return "addelement services {0} '' services:{1}\n".format(groupName, self.name)

class CiscoNatRule(CiscoGroup):
 # Doc: https://supportcenter.checkpoint.com/supportcenter/portal?eventSubmit_doGoviewsolutiondetails=&solutionid=sk39327
 #    => Notes about NAT on load sharing vs high availability
 #
 #modify network_objects host1 add_adtr_rule true
 #modify network_objects host1 NAT NAT
 #modify network_objects host1 NAT:valid_ipaddr|adtr_hide 192.168.1.100
 #modify network_objects host1 NAT:netobj_adtr_method adtr_static
 #modify network_objects host1 NAT:the_firewalling_obj network_objects:gateway1|globals:All
 #update network_objects host1

	"""A cisco nat object"""
	installOn = None
	type = None
	internalObj = None
	externalObj = None
	
	def __init__(self, parsedObj):
		cmd,id,nattedObjName = parsedObj.text.split(' ', 2)
		CiscoGroup.__init__(self,nattedObjName)
		self.dbClass = ''
		self.installOn = DEFAULT_INSTALLON
		
		obj = self._getMemberObj('object',nattedObjName)
		if obj:
			self.internalObj = obj
		else:
			raise C2CException('Cannot find nat internal object %s' % nattedObjName)
		
		child = self._parseChildren(parsedObj)
		# For all network objects
		if child.has_key('nat'):
			for network in child['nat']:
				# Possible values of network-object:
				# nat (dmz-1,SCNET) dynamic 205.192.153.9
				# nat (inside,SCNET) dynamic obj-205.192.153.10-205.192.153.254
				# nat (dmz-1,outside) static 69.17.147.172
				zones,type,natIp = network.split(' ',2)
				obj = self._getMemberObj(type,natIp)
				if obj == None:
					self._createMemberObj(type,natIp)
					obj = self._getMemberObj(type,natIp)

				self.externalObj = obj
				self.type = type
				
		if child.has_key('description'):
			self.desc = child['description'][0]
		
	def toString(self, indent=''):
		return indent+self.getClass()+"(Type=%s,InternalIP=%s,ExternalIP=%s,alias=%s)\n" % (self.type,self.internalObj.name,self.externalObj.name,','.join(self.alias))

	def toDBEdit(self):
		return '''# Creating new nat rule: {0}
 modify network_objects {0} add_adtr_rule true
 modify network_objects {0} NAT NAT
 modify network_objects {0} NAT:valid_ipaddr {1}
 modify network_objects {0} NAT:netobj_adtr_method adtr_static
 modify network_objects {0} NAT:the_firewalling_obj network_objects:{2}
 update network_objects {0}
 '''.format(self.internalObj.name, self.externalObj.ipAddr, self.installOn)

	def toDBEditElement(self, groupName):
		return "addelement network_objects {0} '' network_objects:{1}\n".format(groupName, self.name)

class CiscoFwRule(CiscoGroup):
 # Doc: https://sc1.checkpoint.com/documents/R77/CP_R77_CLI_ReferenceGuide_WebAdmin/105997.htm
 # Creating new rule: {0}
 # addelement fw_policies ##{1} rule security_rule
 # modify fw_policies ##{1} rule:0:comments "{2}"
 # modify fw_policies ##{1} rule:0:disabled false
 # rmbyindex fw_policies ##{1} rule:0:track 0
 # addelement fw_policies ##{1} rule:0:track tracks:None
 # addelement fw_policies ##{1} rule:0:time globals:Any
 # addelement fw_policies ##{1} rule:0:install:'' globals:Any
 # rmbyindex fw_policies ##{1} rule:0:action 0
 # addelement fw_policies ##{1} rule:0:action accept_action:accept
 # addelement fw_policies ##{1} rule:0:src:'' globals:Any
 # modify fw_policies ##{1} rule:0:src:op ''
 # addelement fw_policies ##{1} rule:0:dst:'' globals:Any
 # modify fw_policies ##{1} rule:0:dst:op ''
 # addelement fw_policies ##{1} rule:0:services:'' globals:Any
 # modify fw_policies ##{1} rule:0:services:op ''
	src = None
	dst = None
	port = None
	action = None
	time = None
	tracks = None
	installOn = None
	policy = DEFAULT_POLICY
	aclName = None
	disabled = False
	
	def __init__(self, parsedObj, remark=None, policy=None, installOn=None):
		# access-list perim extended permit tcp object-group In-Domain_Servers object-group DM_INLINE_NETWORK_2 object-group In-Domain-TCP 
		a = parsedObj.text.split(' ', 4)
		CiscoGroup.__init__(self,'')
		self.desc = remark
		self.policy = policy
		self.installOn = installOn
		self.src = []
		self.dst = []
		self.port = []
		self._parseACL(parsedObj)
	
	# access-list perim extended permit tcp object-group In-Domain_Servers object-group DM_INLINE_NETWORK_2 object-group In-Domain-TCP 
	# access-list perim extended permit udp object-group All-Perimeter object-group OVOW-servers eq snmptrap 
	# access-list perim extended permit object-group DM_INLINE_SERVICE_4 object-group ExpressWay_Perim object-group Corp_DC 
	def _parseACL(self, parsedObj):
		acl = parsedObj.text.split(' ')
		self.time = self._getTime(acl)
		self.tracks = self._getTracks(acl)
		#self.installOn = self._getInstallOn(acl)
		self.action = self._getAction(acl)
		self.disabled = self._getDisabled(acl)
		self.src,self.dst,self.port = self._getSrcDstPort(acl)
		
	def _getSrcDstPort(self, acl):
		aclName = acl[1]
		proto = acl[4]
		level = 0			# Some kind of index used while parsing. 
		protoIsSpecified = False
		srcObj = None
		dstObj = None
		portObj = None
			
		if proto in SUPPORTED_PROTO:
			protoIsSpecified = True
		
		skipNext = False
		for i in range(4,len(acl)-1):
			if skipNext:
				skipNext = False
			elif protoIsSpecified and (acl[i] in SUPPORTED_OBJ_FLAGS or (isipaddress(acl[i]) and isipaddress(acl[i+1]))) and level == 0:	# src
				srcObj = self._parseSrcDst(acl[i], acl[i+1])
				if not acl[i] in SUPPORTED_ANY_FLAGS:	# Some hack to protect next argument from getting parsed.
					skipNext = True
				level = level + 1
			elif protoIsSpecified and (acl[i] in SUPPORTED_OBJ_FLAGS or (isipaddress(acl[i]) and isipaddress(acl[i+1]))) and level == 1:	# dst
				dstObj = self._parseSrcDst(acl[i], acl[i+1])
				if not acl[i] in SUPPORTED_ANY_FLAGS:	# Some hack to protect next argument from getting parsed.
					skipNext = True
				level = level + 1
			elif protoIsSpecified and acl[i] in SUPPORTED_PORT_FLAGS and level == 2:	# port
				if acl[i] == 'range':
					port = acl[i+1] + ' ' + acl[i+2]
					portObj = self._parsePort(acl[i], port, proto)
					skipNext = True
				else:
					portObj = self._parsePort(acl[i], acl[i+1], proto)
				level += 1

			elif acl[i] in SUPPORTED_OBJ_FLAGS and level == 0:	# port
				portObj = self._parsePort(acl[i], acl[i+1], 'ip')
				level = level + 1
			elif (acl[i] in SUPPORTED_OBJ_FLAGS or (isipaddress(acl[i]) and isipaddress(acl[i+1]))) and level == 1:	# src
				srcObj = self._parseSrcDst(acl[i], acl[i+1])
				level = level + 1
				if not acl[i] in SUPPORTED_ANY_FLAGS:	# Some hack to protect next argument from getting parsed.
					skipNext = True
			elif (acl[i] in SUPPORTED_OBJ_FLAGS or (isipaddress(acl[i]) and isipaddress(acl[i+1]))) and level == 2:	# dst
				dstObj = self._parseSrcDst(acl[i], acl[i+1])
				level = level + 1
				if not acl[i] in SUPPORTED_ANY_FLAGS:	# Some hack to protect next argument from getting parsed.
					skipNext = True
		
		# if last element of access-list is single (e.g. any or any4)
		if dstObj == None and acl[len(acl)-1] in SUPPORTED_ANY_FLAGS:
			dstObj = self._getAnySrcDst()
		
		if srcObj == None:
			print('ACL: ' + ' '.join(acl))
			print('Proto: '+proto)
			print('protoIsSpecified: '+str(protoIsSpecified))
			print('Dst: '+str(dstObj))
			print('Port: '+str(portObj))
			raise C2CException('Source object cannot be null')
		if dstObj == None:
			print('ACL: ' + ' '.join(acl))
			print('Proto: '+proto)
			print('protoIsSpecified: '+str(protoIsSpecified))
			print('Src: '+str(srcObj))
			print('Port: '+str(portObj))
			#print('argument #6: '+str(acl[6]))
			#print('isipaddress: '+str(isipaddress(acl[6])))
			raise C2CException('Destination object cannot be null')
			
		if portObj == None and proto in SUPPORTED_PROTO:
			portObj = self._getAnyPort(proto)
		elif portObj == None:
			portObj = self._getAnyPort('ip')

		return [[srcObj],[dstObj],[portObj]]
		
	def _getAnySrcDst(self):
		obj = self._getMemberObj('host','any')
		if obj == None:
			self._createMemberObj('host','any')
			obj = self._getMemberObj('host','any')
		return obj
			
	def _getAnyPort(self, proto):
		if proto == 'ip':
			type = 'port'
		elif proto == 'icmp':
			type = 'icmp'
		elif proto == 'tcp':
			type = 'port'
		elif proto == 'udp':
			type = 'port'
		elif proto == 'esp':
			type = 'esp'
		elif proto == 'ah':
			type = 'ah'
		else:
			raise C2CException('Cannot find the "any" service for protocol "%s"' %proto)
			
		obj = self._getMemberObj(type,'any')	# port is arbitrary. the "any" port is a little hack.
		if obj == None:
			self._createMemberObj(type,'any')
			obj = self._getMemberObj(type,'any')
		return obj
		
	def _parseSrcDst(self, type, src):
		if type in SUPPORTED_ANY_FLAGS:
			obj = self._getAnySrcDst()
		elif type == 'host':
			obj = self._getMemberObj(type,src)
			if not obj:
				self._createMemberObj(type,src)
				obj = self._getMemberObj(type,src)
		elif isipaddress(type) and isipaddress(src):
			obj = self._getMemberObj('subnet',type,src)
			if not obj:
				self._createMemberObj('subnet',type,src)
				obj = self._getMemberObj('subnet',type,src)
		else:
			c2c = Cisco2Checkpoint.getInstance()
			list = c2c.findObjByName(src)
			obj = self._parseResult(list, src, type)
		return obj
			
	def _parsePort(self, type, portName, proto=None):
		c2c = Cisco2Checkpoint.getInstance()
		if type == 'eq':
			port = self._convertPort(portName)
			if port.isdigit():
				list = c2c.findServiceByNum(proto, port)
			#elif port[0].isdigit() and '-' in port:
			#	first,last = port.split(' ',1)
			#	list = c2c.findServiceByRange(proto, port)
			else:
				raise C2CException('Invalid port: %s' % port)
		elif type == 'range':
			first,last = portName.split(' ',1)
			list = c2c.findServiceByRange(proto, first,last)
		elif type == 'object-group' or type == 'object':
			list = c2c.findServiceGroupByName(portName)
		else:
			raise C2CException('Unknown flag when parsing port from ACL: "%s"' % type)
		obj = self._parseResult(list, portName, type)
		return obj
					
	def _getTime(self, acl):
		return None
		
	def _getTracks(self, acl):
		for i in range(4,len(acl)-2):
			if acl[i] == 'log' and acl[i+1] == 'disable':
				return 'disable'
		return 'enable'
		
	def _getInstallOn(self, acl):
		return DEFAULT_INSTALLON
		
	def _getAction(self, acl):
		action = acl[3]
		if action in ['permit','deny']:
			return action
		else:
			raise C2CException('Action "%s" not supported' % self.action)
			
	def _getDisabled(self, acl):
		if acl[-1:] == 'inactive':
			return True
		else:
			return False
		
	def _getSrcToDBEdit(self, ruleID=0):
		if 'any' in [obj.name for obj in self.src]:
			return "addelement fw_policies ##{0} rule:{1}:src:'' globals:Any\n".format(self.policy, ruleID)
		elif self.src != None:
			ret = ''
			for src in self.src:
				#ret += "rmelement fw_policies ##{0} rule:{1}:src:'' network_objects:{2}\n".format(self.policy, ruleID, self.src.name)
				ret += "addelement fw_policies ##{0} rule:{1}:src:'' network_objects:{2}\n".format(self.policy, ruleID, src.name)
			return ret
		else:
			return ''
			
	def _getDstToDBEdit(self, ruleID=0):
		if 'any' in [obj.name for obj in self.dst]:
			return "addelement fw_policies ##{0} rule:{1}:dst:'' globals:Any\n".format(self.policy, ruleID)
		elif self.dst != None:
			ret = ''
			for dst in self.dst:
				#ret += "rmelement fw_policies ##{0} rule:{1}:dst:'' network_objects:{2}\n".format(self.policy, ruleID, self.dst.name)
				ret += "addelement fw_policies ##{0} rule:{1}:dst:'' network_objects:{2}\n".format(self.policy, ruleID, dst.name)
			return ret
		else:
			return ''
			
	def _getPortToDBEdit(self, ruleID=0):
		if 'any' in [obj.name for obj in self.port] or self.port == None:
			return "addelement fw_policies ##{0} rule:{1}:services:'' globals:Any\n".format(self.policy, ruleID)
		elif self.port != None:
			ret = ''
			for port in self.port:
				#ret += "rmelement fw_policies ##{0} rule:{1}:services:'' services:{2}\n".format(self.policy, ruleID, self.port.name)
				ret += "addelement fw_policies ##{0} rule:{1}:services:'' services:{2}\n".format(self.policy, ruleID, port.name)
			return ret
		else:
			return ''
			
	def _getTimeToDBEdit(self):
		return 'globals:Any'
		
	def _getTracksToDBEdit(self):
		if self.tracks == 'enable':
			return 'tracks:Log'
		elif self.tracks == 'disable':
			return 'tracks:None'
		else:
			return ''
			
	def _getInstallOnToDBEdit(self):
		return 'globals:Any'
		
	def _getActionToDBEdit(self):
		if self.action == 'permit':
			return 'accept_action:accept'
		elif self.action == 'deny':
			return 'drop_action:drop'
		else:
			return ''
			
	def _getDisabledToDBEdit(self):
		if self.disabled:
			return 'true'
		else:
			return 'false'
	
	def _getSrcToString(self):
		return ';'.join([obj.name for obj in self.src])
		
	def _getDstToString(self):
		return ';'.join([obj.name for obj in self.dst])
		
	def _getPortToString(self):
		return ';'.join([obj.name for obj in self.port])
		
	def mergeWith(self, objToMerge):
		for src in objToMerge.src:
			if not src in self.src:
				self.src.append(src)
		for dst in objToMerge.dst:
			if not dst in self.dst:
				self.dst.append(dst)
		for port in objToMerge.port:
			if not port in self.port:
				self.port.append(port)
		
		self.desc = self.getDesc()
		self.desc += " "+objToMerge.getDesc()
			
	def toString(self, indent='', inclChild=True):
		ret = ''
		srcName = self.src.name if not isarray(self.src) else self._getSrcToString()
		dstName = self.dst.name if not isarray(self.dst) else self._getDstToString()
		portName = self.port.name if not isarray(self.port) else self._getPortToString()
		ret += indent+"FWRule(src=%s,dst=%s,port=%s,action=%s,pol=%s,inst=%s,desc=%s)\n" % (srcName,dstName,portName,self.action,self.policy,self.installOn,self.getDesc())
		if inclChild:
			for src in self.src:
				ret += indent+" Src:"+src.toString(' ')
			for dst in self.dst:
				ret += indent+" Dst:"+dst.toString(' ')
			for port in self.port:
				ret += indent+" Port:"+port.toString(' ')
		return ret

	def toDBEdit(self):
		global FW_RULE_INDEX
		FW_RULE_INDEX = FW_RULE_INDEX + 1
		return '''# Creating new rule: {0}
 #addelement fw_policies ##{1} rule security_rule
 modify fw_policies ##{1} rule:{11}:comments "{2}"
 modify fw_policies ##{1} rule:{11}:disabled {10}
 rmbyindex fw_policies ##{1} rule:{11}:track 0
 addelement fw_policies ##{1} rule:{11}:track {3}
 addelement fw_policies ##{1} rule:{11}:time {4}
 addelement fw_policies ##{1} rule:{11}:install:'' {5}
 rmbyindex fw_policies ##{1} rule:{11}:action 0
 addelement fw_policies ##{1} rule:{11}:action {6}
 {7} modify fw_policies ##{1} rule:{11}:src:op ''
 {8} modify fw_policies ##{1} rule:{11}:dst:op ''
 {9} modify fw_policies ##{1} rule:{11}:services:op ''
 '''.format(self.name, \
			self.policy, \
			self.getDesc(), \
			self._getTracksToDBEdit(), \
			self._getTimeToDBEdit(), \
			self._getInstallOnToDBEdit(), \
			self._getActionToDBEdit(), \
			self._getSrcToDBEdit(FW_RULE_INDEX), \
			self._getDstToDBEdit(FW_RULE_INDEX), \
			self._getPortToDBEdit(FW_RULE_INDEX), \
			self._getDisabledToDBEdit(), \
			FW_RULE_INDEX)		

@Singleton	
class CiscoParser():
	configFile = None
	parse = None
	
	def __init__(self):
		pass
	
	def parse(self,configFile):
		self.configFile = configFile
		self.parse = CiscoConfParse(configFile)
					
	def getAllObjs(self):
		return self.getNameObjs() + \
				self.getHostObjs() + \
				self.getNetObjs() + \
				self.getRangeObjs()
				
	def getAllGroups(self):
		return	self.getNetGroups() + \
				self.getPortGroups()
				
	def getNameObjs(self):
		return [obj for obj in self.parse.find_objects("^name")]
		
	def getHostObjs(self):
		return [obj for obj in self.parse.find_objects(r"^object\snetwork") \
					if obj.re_search_children(r"host")]

	def getNetObjs(self):
		return [obj for obj in self.parse.find_objects(r"^object\snetwork") \
					if obj.re_search_children(r"subnet")]

	def getRangeObjs(self):
		return [obj for obj in self.parse.find_objects(r"^object\snetwork") \
					if obj.re_search_children(r"range")]
		
	def getNetGroups(self):
		return [obj for obj in self.parse.find_objects(r"^object-group\snetwork")]
					
	def getPortGroups(self):
		return [obj for obj in self.parse.find_objects(r"^object-group\sservice")] + \
				[obj for obj in self.parse.find_objects(r"^object-group\sicmp-type")] + \
				[obj for obj in self.parse.find_objects(r"^object-group\sprotocol")]
	
	def getNatRules(self):
		return [obj for obj in self.parse.find_objects(r"^object\snetwork") \
					if obj.re_search_children(r"nat")]	
					
	def getFwRules(self):
		return [obj for obj in self.parse.find_objects(r"^access-list")]	
	
@Singleton	
class Cisco2Checkpoint(CiscoObject):

	obj_list = []
	configFile = None
	policy = None
	installOn = None
	
	nameInCt = None
	nameCt = None
	hostInCt = None
	hostCt = None
	netInCt = None
	netCt = None
	rangeInCt = None
	rangeCt = None
	cpPortsInCt = None
	cpPortsCt = None
	netGrInCt = None
	netGrCt = None
	portGrCt = None
	natRuCt = None
	fwRuInCt = None
	fwRuCt = None

	def __init__(self):
		pass
		
	def importConfig(self,xmlPortsFile,configFile):
		self.obj_list = []
		self.configFile = configFile
		p = CiscoParser.getInstance()
		p.parse(configFile)
		print(MSG_PREFIX+'Importing all objects except groups.')
		self._importHosts(p.getHostObjs())
		self._importNets(p.getNetObjs())
		self._importRanges(p.getRangeObjs())
		#self._importNames(p.getNameObjs())
		self._fixDuplicateNames()
		self._fixDuplicateIp()
		self._fixDuplicateSubnet()
		self._fixDuplicateRange()
		self._importCheckpointPorts(xmlPortsFile)
		self._importNetGroups(p.getNetGroups())	
		#self._fixDuplicateNetGroups()					# Need to fix before uncomment.
		self._importPortGroups(p.getPortGroups())
		self._importNatRules(p.getNatRules())
		self._importFWRules(p.getFwRules())
		self._fixFwRuleRedundancy()

	def _importNames(self, names):
		print(MSG_PREFIX+'Importing all names.')
		self.nameInCt = 0
		for n in names:
			self.addObj(CiscoName(n))
			self.nameInCt += 1
		
	def _importHosts(self, hosts):
		print(MSG_PREFIX+'Importing all hosts.')
		self.hostInCt = 0
		for h in hosts:
			self.addObj(CiscoHost(h))
			self.hostInCt += 1

	def _importNets(self, networks):
		print(MSG_PREFIX+'Importing all networks.')
		self.netInCt = 0
		for n in networks:
			self.addObj(CiscoNet(n))
			self.netInCt += 1

	def _importRanges(self, ranges):
		print(MSG_PREFIX+'Importing all ranges.')
		self.rangeInCt = 0
		for r in ranges:
			self.addObj(CiscoRange(r))
			self.rangeInCt += 1
			
	def _importNetGroups(self, groups):
		print(MSG_PREFIX+'Importing all net/host/range groups.')
		self.netGrInCt = 0
		for newGrp in groups:					
			self.addObj(CiscoNetGroup(newGrp))	
			self.netGrInCt += 1
			
	def _importPortGroups(self, groups):
		print(MSG_PREFIX+'Importing all port groups.')
		self.portGrCt = 0
		for newGrp in groups:		
			self.addObj(CiscoPortGroup(newGrp))		
			self.portGrCt += 1
			
	def _importNatRules(self, rules):
		print(MSG_PREFIX+'Importing all NAT rules.')
		self.natRuCt = 0
		for r in rules:		
			self.addObj(CiscoNatRule(r))	
			self.natRuCt += 1
			
	def _importFWRules(self, rules):
		print(MSG_PREFIX+'Importing all firewall rules.')
		self.fwRuInCt = 0
		comment = None
		for i in range(0,len(rules)-1):	
			cmd,aclName,type,rest = rules[i].text.split(' ', 3)
			if type == 'remark':
				comment = rest
			elif type == 'extended':
				self.addObj(CiscoFwRule(rules[i], comment, self.policy, self.installOn))
				self.fwRuInCt += 1
				comment = None
			else:
				raise C2CException('Invalid ACL type. It should be extended or remark only. Value was: "%s"' % type)

	def _importCheckpointPorts(self, xmlPortsFile):
		tree = et.parse(xmlPortsFile)
		for dict_el in tree.iterfind('services_object'):
			p = dict_el.find('port')
			t = dict_el.find('type')
			c = dict_el.find('comments')
			name,port,proto,comments = None,'','',''
			
			if dict_el.text != None: name = dict_el.text.rstrip()
			if p != None: port = p.text.rstrip()
			if t != None: proto = t.text.lower().rstrip()
			if c != None: comments = c.text
			
			if not (name in EXCLUDE_PORTS):
				if port != '' and port.isdigit() and proto in SUPPORTED_PROTO:
					if port[0] == '>':
						self.addObj(CiscoPortRange(None, name, proto, first, '65535', comments, True))
					elif port[0] == '<':
						self.addObj(CiscoPortRange(None, name, proto, '0', port, comments, True))
					elif '-' in port:
						first,last = port.split('-',1)
						self.addObj(CiscoPortRange(None, name, proto, first, last, comments, True))
					else:
						self.addObj(CiscoSinglePort(None, name, proto, port, comments, True))	
				elif port == '' and proto == 'icmp':
					self.addObj(CiscoIcmp(name, comments, True))
				
		self._addIcmpAlias()
	
	def _addIcmpAlias(self):
		# Translate cisco value => checkpoint value
		print(MSG_PREFIX+'Adding ICMP Aliases')
		for icmpObj in [obj for obj in self.obj_list if obj.getClass() == 'CiscoIcmp']:
			for i, j in ICMP_DIC.iteritems():
				if icmpObj.name == j:
					#if C2C_DEBUG: print(WARN_PREFIX+'Adding "%s" alias to "%s"' % (i,j))
					icmpObj.addAlias(i)
		
	def _fixDuplicateNames(self):
		print(MSG_PREFIX+'Fixing duplicate names')
		for obj in self.obj_list:
			foundList = self.findObjByName(obj.name)
			self._fixDuplicate(foundList, obj.name, obj.getClass())
		self.nameCt = len(self.findObjByType(['CiscoName']))
		self.hostCt = len(self.findObjByType(['CiscoHost']))

	def _fixDuplicateIp(self):
		print(MSG_PREFIX+'Fixing duplicate IP addresses')
		for obj in self.obj_list:
			if obj.getClass() in ['CiscoName','CiscoHost']:
				foundList = self.findHostByAddr(obj.ipAddr)
				self._fixDuplicate(foundList, obj.ipAddr, obj.getClass())
		self.nameCt = len(self.findObjByType(['CiscoName']))
		self.hostCt = len(self.findObjByType(['CiscoHost']))
						
	def _fixDuplicateSubnet(self):
		print(MSG_PREFIX+'Fixing duplicate subnets')
		for obj in self.obj_list:
			if obj.getClass() in ['CiscoNet']:
				foundList = self.findNetByAddr(obj.ipAddr, obj.mask)
				self._fixDuplicate(foundList, obj.ipAddr+'/'+obj.mask, obj.getClass())
		self.netCt = len(self.findObjByType(['CiscoNet']))

	def _fixDuplicateRange(self):
		print(MSG_PREFIX+'Fixing duplicate ranges')
		for obj in self.obj_list:
			if obj.getClass() in ['CiscoRange']:
				foundList = self.findRangeByAddr(obj.first, obj.last)
				self._fixDuplicate(foundList, obj.first+'-'+obj.last, obj.getClass())
		self.rangeCt = len(self.findObjByType(['CiscoRange']))

	def _fixDuplicateNetGroups(self):
		print(MSG_PREFIX+'Fixing duplicate network groups')
		for obj in self.obj_list:
			if obj.getClass() in ['CiscoNetGroup']:
				foundList = self.findDuplicateNetGroup(obj)
				self._fixDuplicate(foundList, obj.name, obj.getClass())
		self.netGrCt = len(self.findObjByType(['CiscoNetGroup']))
		
	def _fixDuplicate(self, foundList, objName, objType):
		if len(foundList) == 1:
			pass
			#if C2C_DEBUG: print(MSG_PREFIX+'  %s: OK' % objName)
		else:
			if C2C_DEBUG: print(WARN_PREFIX+'  Object %s (%s) was found %i times. Deleting duplicates.' % (objName,objType,len(foundList)))
			if C2C_DEBUG: print(WARN_PREFIX+'    Keeping: %s (%s)' % (foundList[0].name,foundList[0].getClass()))
			for objToDel in foundList[1:]:
				self._cleanObj(foundList[0], objToDel)

	def _fixFwRuleRedundancy(self):
		print(MSG_PREFIX+'Merging redundant FW rules')
		fwRules = [obj for obj in self.obj_list \
					 if obj.getClass() == 'CiscoFwRule']
		
		for i in range(0,len(fwRules)-2):
			for j in range(i+1,len(fwRules)-2):
				if self._areMergable(fwRules[i], fwRules[j]):
					self._mergeRules(fwRules[i], fwRules[j])
					if fwRules[j] in self.obj_list:
						self.removeObj(fwRules[j])
		self.fwRuCt = len(self.findObjByType(['CiscoFwRule']))
		
	def _areMergable(self, obj1, obj2):
		# Conditions for merged
		# 1- Same([src, dst, action, tracks, installOn, time, policy), Different(port)
		# 2- Same([src, port, action, tracks, installOn, time, policy), Different(dst)
		# 3- Same([dst, port, action, tracks, installOn, time, policy), Different(src)
		if (obj1.src == obj2.src and obj1.dst == obj2.dst and obj1.action == obj2.action \
			and obj1.tracks == obj2.tracks and obj1.installOn == obj2.installOn \
			 and obj1.time == obj2.time and obj1.policy == obj2.policy) \
			 or \
		   (obj1.src == obj2.src and obj1.port == obj2.port and obj1.action == obj2.action \
			 and obj1.tracks == obj2.tracks and obj1.installOn == obj2.installOn \
			 and obj1.time == obj2.time and obj1.policy == obj2.policy) \
			 or \
		   (obj1.dst == obj2.dst and obj1.port == obj2.port and obj1.action == obj2.action \
			 and obj1.tracks == obj2.tracks and obj1.installOn == obj2.installOn \
			 and obj1.time == obj2.time and obj1.policy == obj2.policy):
			return True
		else:
			return False
			
	def _mergeRules(self, obj1, obj2):
		# Merge in obj1. obj2 will be deleted.
		#print(WARN_PREFIX+'  The following objects will be merged.')
		print(WARN_PREFIX+'Merging: %s' % obj1.toString('', False))
		print(WARN_PREFIX+'With: %s' % obj2.toString('', False))
		obj1.mergeWith(obj2)
	
	def _cleanObj(self, objToKeep, objToDel):
		for alias in objToDel.alias:
			objToKeep.addAlias(alias)
		objToKeep.addAlias(objToDel.name)
		if C2C_DEBUG: print(WARN_PREFIX+'    Deleting object: %s (%s)' % (objToDel.name, objToDel.getClass()))
		self.removeObj(objToDel)
		
	def findObjByType(self,types):
		return [obj for obj in self.obj_list if (obj.getClass() in types)]
		
	def findObjByNameType(self,name,types):
		return [obj for obj in self.obj_list if (obj.getClass() in types \
					and (obj.name == name or name in obj.alias))]
		
	def findObjByName(self,name):
		return [obj for obj in self.obj_list \
					if (not obj.getClass() in ['CiscoSinglePort','CiscoPortRange','CiscoNatRule','CiscoAnyPort','CiscoIcmp','CiscoAnyIcmp','CiscoEspProto','CiscoAHProto'] \
						and (obj.name == name or name in obj.alias))]
	
	def findHostByAddr(self,ipAddr):
		return [obj for obj in self.obj_list \
					if (obj.getClass() in ['CiscoName','CiscoHost','CiscoAnyHost'] \
						and obj.ipAddr == ipAddr)]
						
	def findNetByAddr(self,ipAddr,mask):
		return [obj for obj in self.obj_list \
					if (obj.getClass() == 'CiscoNet') \
						and obj.ipAddr == ipAddr and obj.mask == mask]
						
	def findRangeByAddr(self,first,last):
		return [obj for obj in self.obj_list \
					if (obj.getClass() == 'CiscoRange') \
						and obj.first == first and obj.last == last]
						
	def findServiceByNum(self,proto,port):
		return [obj for obj in self.obj_list \
					if (obj.getClass() == 'CiscoSinglePort') \
						and obj.proto == proto and obj.port == port]
	
	def findServiceByRange(self,proto,first,last):
		return [obj for obj in self.obj_list \
					if (obj.getClass() == 'CiscoPortRange') \
						and obj.proto == proto and obj.first == first and obj.last == last]
	
	def findServiceByName(self, name):
		return [obj for obj in self.obj_list \
					if (obj.getClass() in ['CiscoSinglePort','CiscoPortRange','CiscoPortGroup','CiscoAnyPort','CiscoIcmp','CiscoAnyIcmp','CiscoEspProto','CiscoAHProto'] \
						and obj.name == name or name in obj.alias)]
	
	def findIPServiceByName(self, name):
		return [obj for obj in self.obj_list \
					if (obj.getClass() in ['CiscoSinglePort','CiscoPortRange','CiscoPortGroup','CiscoAnyPort','CiscoIcmp','CiscoAnyIcmp'] \
						and obj.name == name or name in obj.alias)]
						
	def findServiceGroupByName(self,name):
		return [obj for obj in self.obj_list \
					if (obj.getClass() == 'CiscoPortGroup') \
						and (obj.name == name or name in obj.alias)]
				
	def findIcmpByName(self, name):
		return [obj for obj in self.obj_list \
					if (obj.getClass() == 'CiscoIcmp' or obj.getClass() == 'CiscoAnyIcmp') \
						and (obj.name == name or name in obj.alias)]
						
	def findRuleByDesc(self, desc):
		return [obj for obj in self.obj_list \
				if (obj.getClass() == 'CiscoFwRule' and obj.desc == desc)]
				
	def findDuplicateNetGroup(self, obj2):
		return [obj1 for obj1 in self.obj_list if (obj1.getClass() == 'CiscoNetGroup' and obj1.isEqual(obj2))]
				
	def addObj(self,obj):
		self.obj_list.append(obj)
		
	def removeObj(self,obj):
		self.obj_list.remove(obj)
		
	def setPolicy(self, policy):
		self.policy = policy
		
	def setInstallOn(self, installOn):
		self.installOn = installOn
		
	def setDebug(self, debug):
		if debug:
			global C2C_DEBUG
			C2C_DEBUG = True
	
	def getAllObjs(self):
		return ''.join([obj.toString() for obj in self.obj_list if obj.alreadyExist == False])
		
	def getAllHosts(self):
		return ''.join([obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoHost' or obj.getClass() == 'CiscoName')])
			
	def getAllPorts(self):
		return ''.join([obj.toString() for obj in self.obj_list if (obj.getClass() in ['CiscoSinglePort', 'CiscoPortRange'])])

	def getAllNonNumPorts(self):
		return ''.join([obj.toString() for obj in self.obj_list if ((obj.getClass() == 'CiscoSinglePort') and (not obj.port.isdigit()))])
		
	def getAllPortGroups(self):
		return ''.join([obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoPortGroup')])

	def getAlreadyExistPorts(self):
		return ''.join([obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoSinglePort' and obj.alreadyExist == True)] + \
					[obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoPortRange' and obj.alreadyExist == True )])

	def getNewPorts(self):
		return ''.join([obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoSinglePort' and obj.alreadyExist == False)] + \
					[obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoPortRange' and obj.alreadyExist == False )])
					
	def getAllIcmp(self):
		return ''.join([obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoIcmp')])

	def getNatRules(self):
		return ''.join([obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoNatRule')])	
		
	def getFWRules(self):
		return ''.join([obj.toString() for obj in self.obj_list if (obj.getClass() == 'CiscoFwRule')])						
						
	def getSummary(self):
		# Print summary what was parsed.
		print("""#
# Summary of the findings in "{0}"
#
# Number of hosts (before merge): {3}
# Number of hosts (after merge): {4}
# Number of subnet (before merge): {5}
# Number of subnet (after merge): {6}
# Number of range (before merge): {7}
# Number of range (after merge): {8}
# Number of subnet groups: {9}
# Number of service groups: {10}
# Number of nat rules: {11}
# Number of fw rules (before merge): {12}
# Number of fw rules (after merge): {13}
#""".format( self.configFile, \
			self.nameInCt, \
			self.nameCt, \
			self.hostInCt, \
			self.hostCt, \
			self.netInCt, \
			self.netCt, \
			self.rangeInCt, \
			self.rangeCt, \
			self.netGrCt, \
			self.portGrCt, \
			self.natRuCt, \
			self.fwRuInCt, \
			self.fwRuCt \
	))
	
	def toDBEdit(self):
		return ''.join([obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoName')] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoHost' and obj.alreadyExist == False)] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoNet')] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoRange')] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoNetGroup')] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoSinglePort' and obj.alreadyExist == False)] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoPortRange' and obj.alreadyExist == False)] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoPortGroup')] + \
				["# Enable global properties NAT ip pool\n"] + \
				["modify properties firewall_properties enable_ip_pool true\n"] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoNatRule') and obj.type == 'static'] + \
				[obj.toDBEdit() for obj in self.obj_list if (obj.getClass() == 'CiscoFwRule')]) + \
				"update_all"
		

		
		
		