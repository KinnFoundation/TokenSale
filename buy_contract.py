from pyteal import *
from pyteal.ast.bytes import Bytes
from pyteal_helpers import program


def approval():
    # globals
    asset_id = Bytes("aid")  # uint64

    op_buy_px = Bytes("buy")
    op_optin = Bytes("opt")

    is_creator = Txn.sender() == Global.creator_address()

    on_creation = Seq(  # no risk
        [
            Assert(Txn.application_args.length() == Int(1)),  # limit the number of txn args for security
            App.globalPut(asset_id, Btoi(Txn.application_args[0])),  # limits the contract to one token from the beninging
            Return(Int(1)),
        ]
    )

    opt_in = Seq(  # private
        # only the creator can use this, low risk, otherwise people may opt the contract into a bunch of things
        [   
            Assert(is_creator),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_receiver: Global.current_application_address(),
                TxnField.asset_amount: Int(0),
                TxnField.xfer_asset: Txn.assets[0], # Must be in the assets array sent as part of the application call
            }),
            InnerTxnBuilder.Submit(),
            Approve(),
        ]
    )

    buy_px = Seq(  # public
        [   
            # Safety Checks
            Assert(Global.group_size() == Int(2)),  # Gtxn[0] is the payment, [1] is the noop
            Assert(Gtxn[0].fee() <= Int(5000)),  # 5000 in case of congestion
            Assert(Gtxn[1].fee() <= Int(5000)),  
            Assert(Gtxn[0].lease() == Global.zero_address()),  # no leases
            Assert(Gtxn[1].lease() == Global.zero_address()),
            Assert(Gtxn[0].rekey_to() == Global.zero_address()),  # no rekeys
            Assert(Gtxn[1].rekey_to() == Global.zero_address()),
            Assert(Gtxn[0].close_remainder_to() == Global.zero_address()),   # only on pay txns
            # don't have to worry about closeouts, neither group txn is an asset transfer
            # should be fine to just check the txn type because only opted into 1 asset (sending algos is fine too I guess)
            Assert(Gtxn[0].type_enum() == TxnType.Payment),
            Assert(Gtxn[1].type_enum() == TxnType.ApplicationCall),
            # make sure they're sending assets only to the receiver addr
            Assert(Gtxn[0].receiver() ==  Global.creator_address()),  # give algo to me so contract doesn't hold it
            Assert(Gtxn[0].amount() >= Int(250000)), # microalgos, make sure they are purchasing greater than the minimum qt.
            Assert(Gtxn[1].application_args.length() == Int(1)),  # need one for the noop buy_px

            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_receiver: Gtxn[0].sender(),  # send to the addr that paid the algo
                TxnField.asset_amount: Gtxn[0].amount()*Int(4),  # automatically applies floor function, /250000 if no decimals (25000-499999 --> 1, 500000-999999 --> 2)
                TxnField.xfer_asset: Gtxn[1].assets[0], # Must be in the assets array sent as part of the application call
            }),
            InnerTxnBuilder.Submit(),
            Approve(),
        ]
    )

    return program.event(
        init=Seq(
            [
                on_creation,
                Approve(),
            ]
        ),
        no_op=Cond(
            [Txn.application_args[0] == op_buy_px, buy_px],
            [Txn.application_args[0] == op_optin, opt_in],
        ),
    )

def clear():
    return Approve()

if __name__ == "__main__":
    with open("buy_approval.teal", "w") as f:
        compiled = compileTeal(approval(), mode=Mode.Application, version=5)
        f.write(compiled)

    with open("buy_clear_state.teal", "w") as f:
        compiled = compileTeal(clear(), mode=Mode.Application, version=5)
        f.write(compiled)
