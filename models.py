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

class stock_picking(models.Model):
	_inherit = 'stock.picking'

	
	project_id = fields.Many2one(comodel_name='project.project')

class res_users(models.Model):
	_inherit = 'res.users'

	project_id = fields.Many2one(comodel_name='project.project')

class project_materials(models.Model):
	_name = 'project.materials'

	@api.one
	def _compute_qty_consumed(self):
		return_value = 0
		if self.project_id:
			return_value = self.project_id._consumed_materials(qty=0,product_id = self.product_id.id)
		self.qty_consumed = return_value 

	@api.one
	def _compute_qty_delivered(self):
		return_value = 0
		if self.project_id:
			return_value = self.project_id._delivered_materials(qty=0,product_id = self.product_id.id)
		self.qty_delivered = return_value 


	project_id = fields.Many2one('project.project')
	product_id = fields.Many2one('product.product',string='Producto')
	qty_budget = fields.Float(string='Cantidad Presupuestada')
	qty_consumed = fields.Float(string='Cantidad Ordenada',compute=_compute_qty_consumed)
	qty_delivered = fields.Float(string='Cantidad Entregada',compute=_compute_qty_delivered)

class project_project(models.Model):
	_inherit = 'project.project'

	material_ids = fields.One2many(comodel_name='project.materials',inverse_name='project_id',readonly=True,\
			states={'draft': [('readonly', False)],'open': [('readonly', False)]})

	@api.multi
	def _consumed_materials(self,qty = 0, product_id = None):
		if not self.ensure_one():
			return None
		purchase_lines = self.env['purchase.order.line'].search([('account_analytic_id','=',self.analytic_account_id.id),\
					('product_id','=',product_id)])
		return_value = 0
		for line in purchase_lines:
			if line.order_id.state in ['purchase','done']:
				return_value = return_value + line.product_qty
		qty = qty + return_value
		print qty
		if self.child_ids:
			for project in self.child_ids:
				return project._consumed_materials(qty = qty, product_id = product_id)
		return qty

	@api.multi
	def _delivered_materials(self,qty = 0, product_id = None):
		if not self.ensure_one():
			return None
		purchase_lines = self.env['purchase.order.line'].search([('account_analytic_id','=',self.analytic_account_id.id),\
					('product_id','=',product_id)])
		return_value = 0
		for line in purchase_lines:
			if line.order_id.state in ['purchase','done']:
				return_value = return_value + line.qty_received
		qty = qty + return_value
		if self.child_ids:
			for project in self.child_ids:
				return project._delivered_materials(qty = qty, product_id = product_id)
		return qty
