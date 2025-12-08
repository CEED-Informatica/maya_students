from odoo import models, fields, api

class WizardUpdateRelatedCancellationLine(models.TransientModel):
  """
  Linea de anulación relacionada para poder ser actualizada
  """
  _name = "maya_students.wizard_update_related_cancellation_line"
  _description = "Líneas del wizard de anulaciones relacionadas"

  wizard_id = fields.Many2one(
    "maya_students.wizard_update_related_cancellation",
    required=True
  )

  cancellation_id = fields.Many2one(
    "maya_students.cancellation",
    required=True,
    string="Anulación"
  )

  subject_name = fields.Char(related="cancellation_id.subject_name")
  current_situation = fields.Selection(related="cancellation_id.situation")

  new_situation = fields.Selection(
    selection = [('5', 'Quiere continuar'),('6', 'Abandona')],
    string="Nueva situación",
  )

  new_situation_just = fields.Selection(
    selection = [('5', 'Quiere continuar'),('6', 'Abandona'),('7', 'Justificada')],
    string="Nueva situación",
  )

  