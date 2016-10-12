from openerp import models, fields, api, _
from openerp.osv import osv
from openerp.exceptions import except_orm, ValidationError
from StringIO import StringIO
import urllib2, httplib, urlparse, gzip, requests, json
import openerp.addons.decimal_precision as dp
import logging
import datetime
from openerp.fields import Date as newdate

#Get the logger
_logger = logging.getLogger(__name__)

class project_materials(models.Model):
	_name = 'project.materials'

	project_id = fields.Many2one('project.project')
	product_id = fields.Many2one('product.product')
	qty_budget = fields.Float(string='Cantidad Presupuestada')
	qty_consumed = fields.Float(string='Cantidad Consumida',readonly=True)

class project_project(models.Model):
	_inherit = 'project.project'

	material_ids = fields.One2many(comodel_name='project.materials',inverse_name='project_id')
