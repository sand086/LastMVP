import React from 'react';
import { Loader2 } from 'lucide-react';
import {
    Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter,
} from '../ui/dialog';
import {
    AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
    AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '../ui/alert-dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../ui/select';

/**
 * Dialogo para cambiar el proveedor de una ruta (+ confirmacion para rutas cerradas).
 * Extraido de JourneyDetail para reducir el tamano del orquestador principal.
 */
export const ProviderEditDialogs = ({
    // Edit dialog
    showProviderEdit,
    setShowProviderEdit,
    selectedProvider,
    setSelectedProvider,
    providersList,
    handleSaveProvider,
    providerEditSaving,
    // Confirm dialog (closed routes)
    showProviderConfirm,
    setShowProviderConfirm,
    doSaveProvider,
}) => (
    <>
        <Dialog open={showProviderEdit} onOpenChange={setShowProviderEdit}>
            <DialogContent className="max-w-sm">
                <DialogHeader>
                    <DialogTitle className="font-heading">Cambiar proveedor de ruta</DialogTitle>
                    <DialogDescription>
                        Este cambio aplica solo a esta ruta. No modifica el driver maestro.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div className="space-y-1">
                        <Label>Proveedor</Label>
                        <Select value={selectedProvider} onValueChange={setSelectedProvider}>
                            <SelectTrigger data-testid="route-provider-select">
                                <SelectValue placeholder="Seleccionar proveedor" />
                            </SelectTrigger>
                            <SelectContent>
                                {providersList.map((p) => (
                                    <SelectItem key={p.id} value={p.id}>
                                        {p.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setShowProviderEdit(false)}>
                        Cancelar
                    </Button>
                    <Button
                        onClick={handleSaveProvider}
                        disabled={providerEditSaving}
                        data-testid="save-route-provider-btn"
                    >
                        {providerEditSaving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                        Guardar
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>

        <AlertDialog open={showProviderConfirm} onOpenChange={setShowProviderConfirm}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle className="font-heading">Ruta completada</AlertDialogTitle>
                    <AlertDialogDescription>
                        Esta ruta ya fue completada. El cambio de proveedor se registrara en el historial de auditoria.
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel>Cancelar</AlertDialogCancel>
                    <AlertDialogAction onClick={doSaveProvider} data-testid="confirm-provider-change-btn">
                        Confirmar cambio
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    </>
);

export default ProviderEditDialogs;
