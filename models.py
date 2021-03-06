from openerp import models, fields, api, _
from openerp.osv import osv
from openerp.exceptions import except_orm, ValidationError
from StringIO import StringIO
import urllib2, httplib, urlparse, gzip, requests, json
import openerp.addons.decimal_precision as dp
import logging
import datetime
from datetime import date
from openerp.fields import Date as newdate

#Get the logger
_logger = logging.getLogger(__name__)

class stock_picking(models.Model):
	_inherit = 'stock.picking'

	"""
	@api.model
	def create(self,vals):
		picking_type = vals.get('picking_type_id',False)
		if picking_type:
			picking_type = self.env['stock.picking.type'].browse(picking_type)
			if picking_type.code in ['internal','outgoing']:
				user = self.env['res.users'].browse(self.env.context['uid'])
				if user.project_id:
					vals['project_id'] = user.project_id.id
                return super(stock_picking, self).create(vals)
	"""
	
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

	@api.one
	def _compute_qty_used(self):
		return_value = 0
		if self.project_id:
			return_value = self.project_id._used_materials(qty=0,product_id = self.product_id.id)
		self.qty_used = return_value 


	project_id = fields.Many2one('project.project')
	product_id = fields.Many2one('product.product',string='Producto')
	qty_budget = fields.Float(string='Cantidad Presupuestada')
	qty_consumed = fields.Float(string='Cantidad Ordenada',compute=_compute_qty_consumed)
	qty_delivered = fields.Float(string='Cantidad Entregada',compute=_compute_qty_delivered)
	qty_used = fields.Float(string='Cantidad Usada',compute=_compute_qty_used)
	tipo_material = fields.Selection([('children','Hijos'),('own','Propio')],default='own')

class purchase_order(models.Model):
	_inherit = 'purchase.order'

	@api.one
	@api.constrains('amount_total')
	def _check_monthly_spend(self):
		user_id = self.env.context['uid']
		user = self.env['res.users'].browse(user_id)
		if user.has_group('purchase.group_purchase_user') or user.has_group('purchase.group_purchase_manager'):
			return True
		for line in self.order_line:		
			if line.price_subtotal > 0 and line.account_analytic_id:
				project = self.env['project.project'].search([('analytic_account_id','=',line.account_analytic_id.id)])
				check_budget = project.check_project_budget
				if not check_budget:
					old_project = project
					while old_project:
						if old_project.check_project_budget:
							check_budget = True
							project = old_project
							break
						old_project = old_project.parent_id
				if project and check_budget:
					user = user_id
					if project.user_id.id != user:
						raise ValidationError('El usuario no se encuentra habilitado para realizar compras en el proyecto seleccionado')
					# import pdb;pdb.set_trace()
					if (project.project_monthly_spend + line.price_subtotal) > project.project_monthly_budget:
						raise ValidationError('El presupuesto mensual para el proyecto ya se encuentra consumido')


class project_project(models.Model):
	_inherit = 'project.project'

	@api.one
	def _compute_monthly_spend(self):
		return_value = 0
		return_value = self._monthly_spend(amount=0)
		self.project_monthly_spend = return_value 

	check_project_budget = fields.Boolean('Controlar Presupuesto',default=False)
	project_monthly_budget = fields.Monetary('Monto presupuestado mensual')
	project_monthly_spend = fields.Monetary('Monto consumido',compute=_compute_monthly_spend)
	material_ids = fields.One2many(comodel_name='project.materials',inverse_name='project_id',readonly=True,\
			states={'draft': [('readonly', False)],'open': [('readonly', False)]})

	@api.multi
	def _monthly_spend(self,amount = 0):
		if not self.ensure_one():
			return None
		purchase_lines = self.env['purchase.order.line'].search([('account_analytic_id','=',self.analytic_account_id.id)])
		return_value = 0
		for line in purchase_lines:
			date_order = line.date_order
			year_order = int(date_order[:4])
			month_order = int(date_order[5:7])
			today = date.today()
			if line.order_id.state in ['purchase','done'] \
				and today.month == month_order \
				and today.year == year_order:
				user = self.env['res.users'].browse(line.order_id.create_uid.id)
				#import pdb;pdb.set_trace()
				if not user.has_group('purchase.group_purchase_user') and not user.has_group('purchase.group_purchase_manager'):
					return_value = return_value + line.price_subtotal
		amount = amount + return_value
		if self.child_ids:
			for project in self.child_ids:
				return project._monthly_spend(amount = amount)
		return amount

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

	@api.multi
	def _used_materials(self,qty=0,product_id = None):
		if not self.ensure_one():
			return None
		pickings = self.env['stock.picking'].search([('project_id','=',self.id),('state','=','done')])
		return_value = 0
		for picking in pickings:
			packs = self.env['stock.pack.operation'].search([('picking_id','=',picking.id),\
					('product_id','=',product_id)])
			for pack in packs:
				return_value = return_value + pack.product_qty
		qty = qty + return_value
		if self.child_ids:
			for project in self.child_ids:
				return project._used_materials(qty = qty, product_id = product_id)
		return qty

	@api.one
	def project_recalculate_materials(self):
		materials = self.env['project.materials'].search([('project_id','=',self.id),('tipo_material','=','children')])
		for material in materials:
			material.unlink()
		materials = self.env['project.materials'].search([('project_id','!=',self.id),('tipo_material','=','own')])
		for material in materials:
			process = True
			original_project_id = material.project_id
			update_flag = False
			while process:
				if not original_project_id.parent_id:
					process = False
				if original_project_id.parent_id.id == self.id:
					update_flag = True
					process =False
				else:
					original_project_id = original_project_id.parent_id
			if update_flag:
				update_id = self.env['project.materials'].search([('product_id','=',material.product_id.id),\
					('project_id','=',self.id),('tipo_material','=','children')])
				if not update_id:
					vals = {
						'project_id': self.id,
						'product_id': material.product_id.id,
						'qty_budget': material.qty_budget,
						'tipo_material': 'children',
						}
					material_id = self.env['project.materials'].create(vals)
				else:
					vals = {
						'qty_budget': update_id.qty_budget + material.qty_budget,
						'tipo_material': 'children',
						}
					update_id.write(vals)
