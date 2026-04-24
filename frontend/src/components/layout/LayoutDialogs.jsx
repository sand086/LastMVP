import React from 'react';
import { format } from 'date-fns';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '../ui/alert-dialog';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Loader2 } from 'lucide-react';

export const LayoutConfirmDialog = ({
    open, onOpenChange,
    selectedDate, selectedClient, clients, routeData, historyData,
    onConfirm, creating,
}) => (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
        <AlertDialogContent>
            <AlertDialogHeader>
                <AlertDialogTitle className="font-heading">
                    Confirmar creación de rutas
                </AlertDialogTitle>
                <AlertDialogDescription>
                    Se crearán rutas con los siguientes datos:
                    <ul className="mt-3 space-y-1 text-slate-700">
                        <li>• Fecha: <strong>{format(selectedDate, 'dd/MM/yyyy')}</strong></li>
                        <li>• Cliente: <strong>{clients.find(c => c.id === selectedClient)?.name}</strong></li>
                        <li>• Rutas: <strong>{routeData?.total_routes}</strong></li>
                        <li>• Mensajeros: <strong>{routeData?.drivers.length}</strong></li>
                        <li>• Órdenes totales: <strong>{historyData?.total_orders}</strong></li>
                    </ul>
                    <p className="mt-3 text-sm text-amber-600">
                        Se omitirán automáticamente órdenes y rutas duplicadas.
                    </p>
                </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                <AlertDialogAction
                    onClick={onConfirm}
                    disabled={creating}
                    data-testid="confirm-create-btn"
                >
                    {creating ? (
                        <>
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            Creando...
                        </>
                    ) : (
                        'Crear rutas'
                    )}
                </AlertDialogAction>
            </AlertDialogFooter>
        </AlertDialogContent>
    </AlertDialog>
);

export const LayoutPendingProviderDialog = ({
    currentPendingIdx, pendingProviders, pendingProviderForm, setPendingProviderForm,
    onCreate, onCancel, creating,
}) => {
    const open = currentPendingIdx >= 0 && currentPendingIdx < pendingProviders.length;
    const current = pendingProviders[currentPendingIdx];
    return (
        <Dialog open={open} onOpenChange={() => {}}>
            <DialogContent
                className="max-w-md"
                onPointerDownOutside={(e) => e.preventDefault()}
                onEscapeKeyDown={(e) => e.preventDefault()}
            >
                <DialogHeader>
                    <DialogTitle className="font-heading text-lg">
                        Proveedor no registrado: {current?.team_name}
                    </DialogTitle>
                    <DialogDescription>
                        {current?.drivers?.length > 1 ? (
                            <>Los drivers <strong>{current?.drivers?.join(', ')}</strong> aparecen asociados al proveedor <strong>{current?.team_name}</strong>, que no existe en el sistema. Crea el proveedor para continuar la carga.</>
                        ) : (
                            <>El driver <strong>{current?.drivers?.[0]}</strong> aparece asociado al proveedor <strong>{current?.team_name}</strong>, que no existe en el sistema. Crea el proveedor para continuar la carga.</>
                        )}
                    </DialogDescription>
                </DialogHeader>
                {currentPendingIdx >= 0 && pendingProviders.length > 1 && (
                    <p className="text-xs text-slate-500">Proveedor {currentPendingIdx + 1} de {pendingProviders.length}</p>
                )}
                <div className="space-y-3">
                    <div className="space-y-1">
                        <Label>Nombre del proveedor *</Label>
                        <Input
                            value={pendingProviderForm.name}
                            onChange={(e) => setPendingProviderForm(p => ({ ...p, name: e.target.value }))}
                            data-testid="pending-provider-name"
                        />
                    </div>
                    <div className="space-y-1">
                        <Label>RFC / Razon social</Label>
                        <Input
                            value={pendingProviderForm.rfc}
                            onChange={(e) => setPendingProviderForm(p => ({ ...p, rfc: e.target.value }))}
                            placeholder="Opcional"
                            data-testid="pending-provider-rfc"
                        />
                    </div>
                    <div className="space-y-1">
                        <Label>Contacto</Label>
                        <Input
                            value={pendingProviderForm.contact_name}
                            onChange={(e) => setPendingProviderForm(p => ({ ...p, contact_name: e.target.value }))}
                            placeholder="Opcional"
                            data-testid="pending-provider-contact"
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onCancel} data-testid="cancel-pending-upload-btn">
                        Cancelar carga
                    </Button>
                    <Button onClick={onCreate} disabled={creating} data-testid="create-pending-provider-btn">
                        {creating && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                        Crear y continuar
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
